import json
import os

import PyPDF2
import gensim.models.doc2vec
import nltk
import numpy as np
import openai
import redis
from dotenv import load_dotenv
from redis.commands.search.field import TagField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

# nltk.download('punkt')

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
openai.organization = os.getenv("OPENAI_ORG")

r = redis.Redis(
    host='redis-12487.c264.ap-south-1-1.ec2.cloud.redislabs.com',
    port=12487,
    password=os.getenv("REDIS_PASSWORD"))

INDEX_NAME = "qa"  # Vector Index Name
DOC_PREFIX = "doc:"  # RediSearch Key Prefix for the Index


def create_index(vector_dimensions: int):
    try:
        r.ft(INDEX_NAME).dropindex(delete_documents=True)
    except:
        pass

    # schema
    schema = (
        TagField("tag"),
        VectorField("vector",  # Vector Field Name
                    "FLAT", {  # Vector Index Type: FLAT or HNSW
                        "TYPE": "FLOAT32",  # FLOAT32 or FLOAT64
                        "DIM": vector_dimensions,  # Number of Vector Dimensions
                        "DISTANCE_METRIC": "COSINE",  # Vector Search Distance Metric
                    }
                    ),
    )

    # index Definition
    definition = IndexDefinition(prefix=[DOC_PREFIX], index_type=IndexType.HASH)

    # create Index
    r.ft(INDEX_NAME).create_index(fields=schema, definition=definition)


def query_openai_chat_completion(messages, functions=None):
    if functions is None:
        functions = []
    completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7,
                                              functions=functions, function_call="auto")
    reply = completion.choices[0].message
    return reply


class Embedding:
    def __init__(self, filename, query, generate_examples=False):
        create_index(300)
        self.filename = filename
        self.query = query
        self.generate_examples = generate_examples
        self.examples = []

    def _read(self):
        text = ""
        name, ext = os.path.splitext(self.filename)
        if ext == ".txt":
            with open(self.filename) as f:
                text = f.read()
        elif ext == ".pdf":
            reader = PyPDF2.PdfReader(self.filename)
            num = reader.numPages
            for i in range(num):
                text += reader.getPage(i).extractText()
        else:
            return ""
        return text

    @staticmethod
    def embed_into_db(page_content, embeddings, tag):
        pipe = r.pipeline()
        for i, (content, embedding) in enumerate(zip(page_content, embeddings)):
            # HSET
            pipe.hset(f"doc:{i}", mapping={
                "vector": embedding,
                "content": content,
                "tag": tag
            })
        pipe.execute()

    @staticmethod
    def get_embedding(text):
        model = gensim.models.doc2vec.Doc2Vec.load('model/new.model')
        return model.infer_vector(text.split())

    @staticmethod
    def convert_embedding_to_structure(embedding):
        return np.array(embedding).astype(np.float32).reshape(1, -1).tobytes()

    @staticmethod
    def format_query(tag, k):
        tag_query = f"(@tag:{{ {tag} }})=>"
        knn_query = f"[KNN {k} @vector $vec AS score]"
        query = Query(tag_query + knn_query) \
            .sort_by('score', asc=False) \
            .return_fields('id', 'score', 'content') \
            .dialect(2)
        return query

    @staticmethod
    def generate_qa_examples(page_content):
        prompt = """
You are a teacher coming up with questions to ask on a quiz. 
Given the following document, please generate a question and answer based on that document.

Example Format:
<Begin Document>
...
<End Document>
QUESTION: question here
ANSWER: answer here

These questions should be detailed and be based explicitly on information in the document. Begin!

<Begin Document>
{doc}
<End Document>
            """
        examples = []
        for doc in page_content[:5]:
            messages = [{
                "role": "user",
                "content": prompt.format(doc=doc)
            }]
            reply = query_openai_chat_completion(messages)
            examples.append(reply)

        return examples


class Character(Embedding):
    def __init__(self, filename, char_count=1000, generate_examples=False):
        super().__init__(filename, self.knn_doc_query_db, generate_examples)
        self.char_count = char_count
        self.chunk_and_embed()

    def chunk(self, text):
        page_content = []
        idx = 0
        s = ""
        for ch in text:
            s += ch
            idx += 1
            if idx >= self.char_count:
                page_content.append(s)
                s = ""
                idx = 0
        return page_content

    def chunk_and_embed(self):
        text = self._read()
        page_content = self.chunk(text)
        if self.generate_examples:
            self.examples = self.generate_qa_examples(page_content)
        embeddings = []
        for content in page_content:
            embedding = self.get_embedding(content.strip())
            embeddings.append(self.convert_embedding_to_structure(embedding))
        self.embed_into_db(page_content, embeddings, "doc")

    def knn_doc_query_db(self, query_term, k=5):
        query = self.format_query("doc", k)
        embedding = self.convert_embedding_to_structure(self.get_embedding(query_term.strip()))
        query_params = {"vec": embedding}
        ret = r.ft(INDEX_NAME).search(query, query_params).docs
        return ret


class Sentence(Embedding):
    def __init__(self, filename, generate_examples=False):
        super().__init__(filename, self.knn_sent_query_db, generate_examples)
        self.chunk_sentences_and_embed()

    def knn_sent_query_db(self, query_term, k=5):
        query = self.format_query("sent", k)
        embedding = self.convert_embedding_to_structure(self.get_embedding(query_term.strip()))
        query_params = {"vec": embedding}
        ret = r.ft(INDEX_NAME).search(query, query_params).docs
        for i, doc in enumerate(ret):
            similiar_sentences = self.get_knn_similiar_sent(doc.content)
            ret[i] = " ".join([doc.content] + [sdoc.content for sdoc in similiar_sentences])
        return ret

    def get_knn_similiar_sent(self, query_term, k=5):
        query = self.format_query("sent", k)
        embedding = self.convert_embedding_to_structure(self.get_embedding(query_term.strip()))
        query_params = {"vec": embedding}
        ret = r.ft(INDEX_NAME).search(query, query_params).docs
        return ret

    @staticmethod
    def chunk_sentences(text):
        tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
        return tokenizer.tokenize(text)

    def chunk_sentences_and_embed(self):
        text = self._read()
        page_content = self.chunk_sentences(text)
        self.examples = self.generate_qa_examples(page_content)
        self.embed_sentences_into_db(page_content)

    def embed_sentences_into_db(self, page_content):
        embeddings = []
        for content in page_content:
            embedding = self.get_embedding(content.strip())
            embeddings.append(self.convert_embedding_to_structure(embedding))
        self.embed_into_db(page_content, embeddings, "sent")


class Memory:
    r = redis.Redis(
        host='redis-12487.c264.ap-south-1-1.ec2.cloud.redislabs.com',
        port=12487,
        password=os.getenv("REDIS_PASSWORD"))

    INDEX_NAME = "chat_history"  # Vector Index Name
    DOC_PREFIX = "doc:"  # RediSearch Key Prefix for the Index

    last_id = -1

    def create_index(self, vector_dimensions: int):
        try:
            self.r.ft(self.INDEX_NAME).dropindex(delete_documents=True)
        except:
            pass

        # schema
        schema = (
            TagField("tag"),
            VectorField("vector",  # Vector Field Name
                        "FLAT", {  # Vector Index Type: FLAT or HNSW
                            "TYPE": "FLOAT32",  # FLOAT32 or FLOAT64
                            "DIM": vector_dimensions,  # Number of Vector Dimensions
                            "DISTANCE_METRIC": "COSINE",  # Vector Search Distance Metric
                        }
                        ),
        )

        # index Definition
        definition = IndexDefinition(prefix=[self.DOC_PREFIX], index_type=IndexType.HASH)

        # create Index
        self.r.ft(self.INDEX_NAME).create_index(fields=schema, definition=definition)

    def add_docs(self, doc):
        self.last_id += 1
        pipe = self.r.pipeline()
        embedding = self.embed(doc)
        # HSET
        pipe.hset(f"doc:{self.last_id}", mapping={
            "vector": embedding,
            "content": doc,
            "tag": 'chat_history'
        })
        pipe.execute()

    def retrieve(self, query_term, k=1):
        tag_query = "(@tag:{ chat_history })=>"
        knn_query = f"[KNN {k} @vector $vec AS score]"
        query = Query(tag_query + knn_query) \
            .sort_by('score', asc=False) \
            .return_fields('id', 'score', 'content') \
            .dialect(2)
        embedding = self.embed(query_term.strip())
        query_params = {"vec": embedding}
        ret = self.r.ft(self.INDEX_NAME).search(query, query_params).docs
        return ret

    @staticmethod
    def embed(doc):
        embeddings = openai.Embedding.create(input=doc.strip(), model="text-embedding-ada-002")["data"][0]["embedding"]
        embeddings = np.array(embeddings, dtype=np.float32).reshape(1, -1).tobytes()
        return embeddings


class Agent:
    def __init__(self, embedding: Embedding, memory: Memory):
        self.embedding = embedding
        self.memory = memory

    def run(self):
        past_events = []
        user_query = input("Query or 0 to exit\n")
        examples_prompt = "\n".join(self.embedding.examples)
        while user_query != "0":
            system_prompt = """
Please provide an answer based solely on the provided sources.
When referencing information from a source,
cite the appropriate source(s) using their corresponding numbers.
Every answer should include at least one source citation.
Only cite a source when you are explicitly referencing it.
If none of the sources are helpful, you should indicate that.
For example:\n
Source 1:\n
The sky is red in the evening and blue in the morning.\n
Source 2:\n
Water is wet when the sky is red.\n
Query: When is water wet?\n
Answer: Water will be wet when the sky is red [2],
which occurs in the evening [1].\n
Use the following pieces of context to answer the users question. 
If you don't know the answer, just say that you don't know, don't try to make up an answer.
Now it's your turn. Below are several numbered sources of information:
----------------
{context}
----------------
Chat history:
{chat_history}
                """
            chat_history = []
            if len(past_events) > 0:
                for msg in past_events[::-1]:
                    retrieved_msg = self.memory.retrieve(msg)[0].content
                    chat_history.append(retrieved_msg)
            user_prompt = f"Question: {user_query}\nHelpful Answer:"
            context = self.embedding.query(user_query)
            system_prompt = "EXAMPLES\n" + examples_prompt + "\n" + system_prompt.format(
                context=context,
                chat_history=chat_history[::-1]
            )
            messages = [
                {
                    "role": "system", "content": system_prompt
                },
                {
                    "role": "user", "content": user_prompt
                }
            ]
            print(system_prompt)
            print(user_prompt)
            tools = [FetchDocument()]
            functions = [tool.schema for tool in tools]
            reply = query_openai_chat_completion(messages, functions).content
            print(reply)
            past_events.append(reply)
            self.memory.add_docs(f"{user_prompt}\n{reply}")
            retrieval_prompt = """
Use fetch_documents to fetch the relevant source docs for the given reply, if no documnets were used just reply saying so, do not make up document ids:
{gpt_reply}
            """
            retrieval_prompt = retrieval_prompt.format(gpt_reply=reply)
            print(retrieval_prompt)
            messages = [
                {
                    "role": "system",
                    "content": retrieval_prompt,

                },
                {
                    "role": "user",
                    "content": "Fetch relevant documents"
                }
            ]
            reply = query_openai_chat_completion(messages, functions).function_call
            print(reply)
            for tool in tools:
                if reply["name"] == tool.schema["name"]:
                    tool.run(json.loads(reply["arguments"]))
                    break
            user_query = input("Query or 0 to exit\n")


class FetchDocument:
    schema = {
        "name": "fetch_dociuments",
        "description": "fetch relevant document content for list of document ids",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {
                        "type": "number"
                    }
                }
            },
            "required": ["ids"]
        }
    }

    @staticmethod
    def run(args):
        ids = args["ids"]
        ids = [f"{DOC_PREFIX}{id}" for id in ids]
        for id in ids:
            print(r.ft(INDEX_NAME).get(id)[0][1])


# e = Sentence('data/sample.txt')
e = Character('data/sample.txt', 1000)
m = Memory()
m.create_index(1536)
agent = Agent(e, m)
agent.run()

import os
import time

import PyPDF2
import gensim.models.doc2vec
import numpy as np
import openai
import redis
import nltk

# noinspection PyUnresolvedReferences
from redis.commands.search.field import TagField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from dotenv import load_dotenv

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


class Embedding:
    def __init__(self, filename, query):
        self.filename = filename
        self.query = query

    @staticmethod
    def _read(filename):
        text = ""
        name, ext = os.path.splitext(filename)
        if ext == ".txt":
            with open(filename) as f:
                text = f.read()
        elif ext == ".pdf":
            reader = PyPDF2.PdfReader(filename)
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


class Char1000(Embedding):
    def __init__(self, filename):
        super().__init__(filename, self.knn_doc_query_db)
        create_index(300)
        self.chunk_1000_and_embed()

    @staticmethod
    def chunk_1000(text):
        page_content = []
        idx = 0
        s = ""
        for ch in text:
            s += ch
            idx += 1
            if idx >= 1000:
                page_content.append(s)
                s = ""
                idx = 0
        return page_content

    def chunk_1000_and_embed(self):
        text = self._read(self.filename)
        page_content = self.chunk_1000(text)
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
    def __init__(self, filename):
        super().__init__(filename, self.knn_sent_query_db)
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
        text = self._read(self.filename)
        page_content = self.chunk_sentences(text)
        self.embed_sentences_into_db(page_content)

    def embed_sentences_into_db(self, page_content):
        embeddings = []
        for content in page_content:
            embedding = self.get_embedding(content.strip())
            embeddings.append(self.convert_embedding_to_structure(embedding))
        self.embed_into_db(page_content, embeddings, "sent")


class Agent:
    def __init__(self, embedding: Embedding):
        self.embedding = embedding

    def run(self):
        chat_history = []
        user_query = input("Query or 0 to exit\n")
        while user_query != "0":
            system_prompt = """
Use the following pieces of context to answer the users question. 
If you don't know the answer, just say that you don't know, don't try to make up an answer.
----------------
{context}
----------------
Chat history:
{chat_history}
                """
            user_prompt = f"Question: {user_query}\nHelpful Answer:"
            system_prompt = system_prompt.format(
                context=self.embedding.query(user_query),
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
            completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, temperature=0.7)
            reply = completion.choices[0].message.content
            print(reply)
            chat_history.append(f"Question:{user_query}\nHelpful Answer:{reply}")
            user_query = input("Query or 0 to exit\n")


e = Sentence('data/sample.txt')
# e = Char1000('data/sample.txt')
agent = Agent(e)
agent.run()

import os

import PyPDF2
import numpy as np
import openai
import redis
# noinspection PyUnresolvedReferences
from redis.commands.search.field import TagField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from dotenv import load_dotenv

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
    r.ft(INDEX_NAME).dropindex(delete_documents=True)
    try:
        # check to see if index exists
        r.ft(INDEX_NAME).info()
        print("Already exists")
    except:
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


def chunk_and_embed(filename):
    reader = PyPDF2.PdfReader(filename)
    count = reader.numPages
    page_content = []
    s = ""
    idx = 0
    for i in range(count):
        page = reader.getPage(i).extractText()
        for char in page:
            s += char
            idx += 1
            if idx >= 1000:
                page_content.append(s)
                s = ""
                idx = 0
    embeddings = []
    for content in page_content:
        embedding = openai.Embedding.create(
            input=content.strip(), model="text-embedding-ada-002"
        )["data"][0]["embedding"]
        embeddings.append(np.array(embedding).astype(np.float32).reshape(1, -1).tobytes())
    pipe = r.pipeline()
    for i, (content, embedding) in enumerate(zip(page_content, embeddings)):
        # HSET
        pipe.hset(f"doc:{i}", mapping={
            "vector": embedding,
            "content": content,
            "tag": "openai"
        })
    res = pipe.execute()


def query_vector_db(query_term):
    query = Query(f'*=>[KNN 2 @vector $vec AS score]') \
        .sort_by('score', asc=False) \
        .paging(0, 2) \
        .return_fields('id', 'score', 'content') \
        .dialect(2)
    embedding = openai.Embedding.create(
        input=query_term.strip(), model="text-embedding-ada-002"
    )["data"][0]["embedding"]
    query_embedding = np.array(embedding).astype(np.float32).reshape(1, -1)
    query_params = {"vec": query_embedding.tobytes()}
    ret = r.ft(INDEX_NAME).search(query, query_params).docs
    print(ret)
    return ret


create_index(1536)
chunk_and_embed('sample2.pdf')


def run():
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
        system_prompt = system_prompt.format(context=query_vector_db(user_query), chat_history=chat_history)
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


run()

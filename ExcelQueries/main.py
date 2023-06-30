import datetime
import json

import pandas as pd
import openai
import os
from datetime import datetime

import redis
from redis.commands.search.field import TextField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
# openai.organization = os.getenv("OPENAI_ORG")

r = redis.Redis(
    host='redis-12487.c264.ap-south-1-1.ec2.cloud.redislabs.com',
    port=12487,
    password=os.getenv("REDIS_PASSWORD"))

INDEX_NAME = "csv"
DOC_PREFIX = "doc:"


def create_index(schema):
    try:
        r.ft(INDEX_NAME).dropindex(delete_documents=True)
    except:
        pass

    # index Definition
    definition = IndexDefinition(prefix=[DOC_PREFIX], index_type=IndexType.HASH)

    # create Index
    r.ft(INDEX_NAME).create_index(fields=schema, definition=definition)


def query_openai_chat_completion(messages, functions=None):
    if functions is None:
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7)
    else:
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7,
                                                  functions=functions, function_call="auto")
    reply = completion.choices[0].message
    return reply


def create_index_of_col(df):
    columns = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        field = None
        if dtype == "object":
            field = TextField(col)
        elif "datetime" in dtype:
            field = NumericField(col)
        elif "int" in dtype or "float" in dtype:
            field = NumericField(col)
        columns.append(field)
    create_index(tuple(columns))


def insert_rows(df):
    rows = []
    for i, row in df.iterrows():
        item = {}
        for col in df.columns:
            if "datetime" in str(df[col].dtype):
                datetime_obj = pd.to_datetime(row[col])
                row[col] = datetime_obj.timestamp()
            item[col] = row[col]
        rows.append(item)
    pipe = r.pipeline()
    for i, row in enumerate(rows):
        pipe.hset(f"doc:{i}", mapping=row)
    pipe.execute()


def get_by_id(ids):
    res = []
    ids = [f"{DOC_PREFIX}{id}" for id in ids]
    for id in ids:
        res.append(r.ft(INDEX_NAME).get(id)[0])

    return res


class Agent:
    prompt = """
You are working with a redis index in python using redis-py. The index iss given by r.ft("{INDEX_NAME}")
The dataframe has the following columns: {{df_columns}}.

The programmer issues commands and you should translate them into Python code. Prefer to use one-liners.

This is the history of your interaction so far:
{chat_history}
Human: {query}

Go!

```Exxample row
{row}
```
Reply in the format:
{{
    "code": string
}}
    """
    chat_history = []

    def __init__(self, file):
        self.df = pd.read_excel(file)
        create_index_of_col(self.df)
        insert_rows(self.df)

    def exec(self, code):
        df = self.df
        ret = eval(code)
        print(ret)

    def run(self):
        user_query = input("Query:")
        row = get_by_id([1])
        sys_prompt = self.prompt.format(INDEX_NAME=INDEX_NAME, chat_history=self.chat_history, query=user_query,
                                        row=row)
        print(sys_prompt)
        messages = [
            {"role": "system", "content": sys_prompt}
        ]
        reply = query_openai_chat_completion(messages).content
        print(reply)
        reply = json.loads(reply)
        code = reply["code"]
        self.exec(code)


agent = Agent('data/data.xlsx')
agent.run()

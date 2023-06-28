import openai
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
openai.organization = os.getenv("OPENAI_ORG")


def query_openai_chat_completion(messages, functions=None):
    if functions is None:
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7)
    else:
        completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7,
                                                  functions=functions, function_call="auto")
    return completion.choices[0].message


class Agent:
    def __init__(self, docs):
        self.docs = docs

    def run(self):
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
        for doc in self.docs[:5]:
            messages = [{
                "role": "user",
                "content": prompt.format(doc=doc)
            }]
            reply = query_openai_chat_completion(messages).content
            examples.append(reply)

        return examples


docs = [
    "ome advanced techniques used in NLP for representing words in a vector format include bag-of-words, "
    "bag-of-n-words, word2vec, and Doc2Vec.",
    "Some disadvantages of representing text as a fixed-length vector include the loss of information about the "
    "semantic relationship between words and the inability to represent words that are closer in meaning, "
    "such as 'powerful' and 'strength'."
]
agent = Agent(docs)
print(agent.run())

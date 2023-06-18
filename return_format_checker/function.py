from dotenv import load_dotenv
import os
import openai
import json

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
openai.organization = os.getenv("OPENAI_ORG")


def query_openai_chat_completion(messages, functions=None):
    if functions is None:
        functions = []
    completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-0613", messages=messages, temperature=0.7,
                                              functions=functions, function_call={"name": Reply().name})
    reply = completion.choices[0].message
    return reply


class Function:
    def __init__(self, name, schema, run):
        self.name = name
        self.schema = schema
        self.run = run


class Reply(Function):
    def __init__(self):
        name = "reply_user"
        schema = {
            "name": name,
            "description": "reply to user's query",
            "parameters": {
                "type": "object",
                "properties": {
                    "reply": {
                        "type": "string",
                    },
                    "reason": {
                        "type": "string"
                    },
                    "user_query": {
                        "type": "string"
                    }
                },
                "required": ["reply", "reason", "user_query"]
            }
        }
        super().__init__(name, schema, self.print_reply)

    @staticmethod
    def print_reply(args):
        return args


class Agent:

    @staticmethod
    def run():
        tools = [Reply()]
        functions = [tool.schema for tool in tools]
        query = input("Query: (0 to exit)")
        sys_prompt = f"""
Only use function_call to reply to use. Do not use content.
            """
        while query != "0":
            user_prompt = f"{query}"
            print(user_prompt)
            messages = [
                {
                    "role": "system", "content": sys_prompt
                },
                {
                    "role": "user", "content": user_prompt
                },
            ]
            reply = query_openai_chat_completion(messages, functions)
            try:
                if reply["function_call"]:
                    for tool in tools:
                        if tool.name == reply["function_call"]["name"]:
                            tool_res = tool.run(json.loads(reply["function_call"]["arguments"]))
                            print(tool_res)
            except KeyError as e:
                print("KeyError:" + str(e))
            query = input("Query: (0 to exit)")


agent = Agent()
agent.run()

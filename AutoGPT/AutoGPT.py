import json
import os
import time
from datetime import datetime

import faiss
import numpy as np
import openai
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()


class SystemMessage:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return "\033[94m" + self.text


class AsstMessage:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return "\033[92m" + self.text


class HumanMessage:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return "\033[96m" + self.text


class Tool:
    def __init__(self, name, description, schema, func=None) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.func = func

    def run(self, args):
        return self.func(args) or None


class Search(Tool):
    def __init__(self) -> None:
        schema = {"query": {"title": "Query", "type": "string"}}
        super().__init__(
            "search",
            "useful for when you need to answer questions about current events. You should ask targeted questions",
            schema,
            self.search
        )

    @staticmethod
    def search(args):
        search = args["query"]
        res = GoogleSearch({
            "q": search,
            "api_key": os.getenv("SERPAPI_API_KEY")
        })
        res = res.get_dict()
        if "answer_box" in res.keys() and "answer" in res["answer_box"].keys():
            toret = res["answer_box"]["answer"]
        elif "answer_box" in res.keys() and "snippet" in res["answer_box"].keys():
            toret = res["answer_box"]["snippet"]
        elif (
                "answer_box" in res.keys()
                and "snippet_highlighted_words" in res["answer_box"].keys()
        ):
            toret = res["answer_box"]["snippet_highlighted_words"][0]
        elif (
                "sports_results" in res.keys()
                and "game_spotlight" in res["sports_results"].keys()
        ):
            toret = res["sports_results"]["game_spotlight"]
        elif (
                "knowledge_graph" in res.keys()
                and "description" in res["knowledge_graph"].keys()
        ):
            toret = res["knowledge_graph"]["description"]
        elif "snippet" in res["organic_results"][0].keys():
            toret = res["organic_results"][0]["snippet"]

        else:
            toret = "No good search result found"
        return toret


class WriteFile(Tool):
    def __init__(self) -> None:
        schema = {
            "file_path": {
                "title": "File Path",
                "description": "name of file",
                "type": "string",
            },
            "text": {
                "title": "Text",
                "description": "text to write to file",
                "type": "string",
            },
        }
        super().__init__("write_file", "Write file to disk", schema, self.write)

    @staticmethod
    def write(args):
        filename = args["file_path"]
        text = args["text"]
        with open(filename, "w") as f:
            f.write(text)
        return f"File {filename} written to successfully"


class ReadFile(Tool):
    def __init__(self) -> None:
        schema = {
            "file_path": {
                "title": "File Path",
                "description": "name of file",
                "type": "string",
            }
        }
        super().__init__("read_file", "Read file from disk", schema, self.read)

    @staticmethod
    def read(args):
        filename = args["file_path"]
        with open(filename, "r") as f:
            return f.read()


class Finish(Tool):
    def __init__(self) -> None:
        schema = {
            "response": "final response to let people know you have finished your objectives"
        }
        super().__init__(
            "finish",
            "Signal that you have finished all your objectives",
            schema,
        )


class Agent:
    def __init__(self, tools, goals, memory=None):
        self.tools = tools
        self.goals = goals
        self.memory = memory
        self.past_events = []

    @staticmethod
    def get_system_setup_prompt() -> str:
        return 'You are Tom, Assistant.\nYour decisions must always be made independently without seeking user ' \
               'assistance.\nPlay to your strengths as an LLM and pursue simple strategies.\nIf you have completed ' \
               'all your tasks, make sure to use the "finish" command.\n\n'

    @staticmethod
    def get_constraints_prompt() -> str:
        return 'Constraints:\n1. ~4000 word limit for short term memory. Your short term memory is short, ' \
               'so immediately save important information to files.\n2. If you are unsure how you previously did ' \
               'something or want to recall past events, thinking about similar events will help you remember.\n3. No ' \
               'user assistance\n4. Exclusively use the commands listed in double quotes e.g. "command name"\n\n'

    @staticmethod
    def get_resources_prompt() -> str:
        return "Resources:\n1. Internet access for searches and information gathering.\n2. Long Term memory " \
               "management.\n3. GPT-3.5 powered Agents for delegation of simple tasks.\n4. File output.\n\n"

    @staticmethod
    def get_perfeval_prompt() -> str:
        return "Performance Evaluation:\n1. Continuously review and analyze your actions to ensure you are performing " \
               "to the best of your abilities.\n2. Constructively self-criticize your big-picture behavior " \
               "constantly.\n3. Reflect on past decisions and strategies to refine your approach.\n4. Every command " \
               "has a cost, so be smart and efficient. Aim to complete tasks in the least number of steps.\n\n"

    @staticmethod
    def get_format_prompt() -> str:
        return """You should only respond in JSON format as described below 
Response Format: 
{
    "thoughts": {
        "text": "thought",
        "reasoning": "reasoning",
        "plan": "- short bulleted - list that conveys - long-term plan",
        "criticism": "constructive self-criticism",
        "speak": "thoughts summary to say to user"
    },
    "command": {
        "name": "command name",
        "args": {
            "arg name": "value"
        }
    }
} 
Ensure the response can be parsed by Python json.loads\n"""

    def get_past_events_prompt(self) -> str:
        date = datetime.now()
        date_prompt = f'The current time and date is {date.strftime("%a")} {date.strftime("%B")} {date.day} {date.time().replace(second=0, microsecond=0)} {date.year}\n'
        prompt = ""
        if len(self.past_events) > 0:
            for msg in self.past_events[::-1]:
                retrieved_msg = self.memory.retrieve(msg)
                prompt += retrieved_msg + ",\n"
        return f"{date_prompt}This reminds you of these events from your past:\n[{prompt}]"

    def get_goals_prompt(self) -> str:
        prompt = "Goals:\n"
        for idx, goal in enumerate(self.goals):
            prompt = f"{prompt}{str(idx + 1)}.{goal}\n"
        return f"{prompt}\n"

    def get_commands_prompt(self) -> str:
        prompt = "Commands:\n"
        for idx, tool in enumerate(self.tools):
            prompt = f"{prompt}{str(idx + 1)}.{tool.name}:{tool.description}, args json schema: {str(tool.schema)}\n"
        return f"{prompt}\n"

    def get_generated_prompt(self) -> str:
        prompt = f"{self.get_system_setup_prompt()}{self.get_goals_prompt()}{self.get_constraints_prompt()}{self.get_commands_prompt()}{self.get_resources_prompt()}{self.get_perfeval_prompt()}{self.get_format_prompt()}{self.get_past_events_prompt()}"
        return prompt

    def run(self):
        self.tools.append(Finish())
        openai.organization = "org-bWPRxgvD4e3jFTVqMKVBiGMp"
        openai.api_key = os.getenv("OPENAI_API_KEY")
        command = ""
        last_tool_res = ""
        while command != "finish":
            prompt = self.get_generated_prompt()
            human_prompt = "Determine which next command to use, and respond using format specified above"
            print(SystemMessage(
                f">Generated prompt:\n{prompt}"))
            messages = [{"role": "system",
                         "content": prompt}]
            if last_tool_res != "":
                print(SystemMessage(last_tool_res))
                messages.append({"role": "system", "content": last_tool_res})
            print(HumanMessage(human_prompt))
            messages.append({"role": "user", "content": human_prompt})
            completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, temperature=0)
            reply = completion.choices[0].message.content
            self.past_events.append(reply)
            print(AsstMessage(f">Assistant Reply:\n{reply}"))
            res_json_dump = json.loads(reply)
            command = res_json_dump["command"]["name"]
            args = res_json_dump["command"]["args"]
            for tool in self.tools:
                if tool.name == command:
                    if tool.name != "finish":
                        last_tool_res = f"Command {tool.name} returned: {tool.run(args)}"
                        self.memory.add_docs(f"{reply}\n{last_tool_res}")
                        time.sleep(20)


class Memory:
    index = faiss.IndexFlatL2(1536)
    docstore = {}
    last_id = -1

    def add_docs(self, doc):
        embedding = self.embed(doc)
        self.docstore[self.last_id + 1] = doc
        self.index.add(embedding)
        self.last_id += 1

    def retrieve(self, query, k=1):
        embedding = self.embed(query)
        _, idx = self.index.search(embedding, k)
        return self.docstore.get(idx[0][0])

    @staticmethod
    def embed(doc):
        embeddings = openai.Embedding.create(input=doc.strip(), model="text-embedding-ada-002")["data"][0]["embedding"]
        embeddings = np.array(embeddings, dtype=np.float32).reshape(1, -1)
        return embeddings


m = Memory()

agent = Agent([Search(), WriteFile()], ["write a weather report on SF"], m)
agent.run()

import json
import os
import time
from typing import List
from datetime import datetime

import openai
from dotenv import load_dotenv


class Tool:
    def __init__(self, name, description, schema) -> None:
        self.name = name
        self.description = description
        self.schema = schema


class Search(Tool):
    def __init__(self) -> None:
        schema = {"query": {"title": "Query", "type": "string"}}
        super().__init__(
            "search",
            "useful for when you need to answer questions about current events. You should ask targeted questions",
            schema,
        )


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
        super().__init__("write_file", "Write file to disk", schema)


class ReadFile(Tool):
    def __init__(self) -> None:
        schema = {
            "file_path": {
                "title": "File Path",
                "description": "name of file",
                "type": "string",
            }
        }
        super().__init__("read_file", "Read file from disk", schema)


class Finish(Tool):
    def __init__(self) -> None:
        schema = {
            "response": "final response to let people know you have finished your objectives"
        }
        super().__init__(
            "finish",
            "use this to signal that you have finished all your objectives",
            schema,
        )


class Agent:
    def __init__(self, tools: List[Tool], goals: List[str]) -> None:
        self.tools = tools
        self.goals = goals
        self.past_events = []

        self.tools.append(Finish())

    @staticmethod
    def get_system_setup_prompt() -> str:
        return 'You are Tom, Assistant.\nYour decisions must always be made independently without seeking user ' \
               'assistance.\nPlay to your strengths as an LLM and pursue simple strategies with no legal ' \
               'complications.\nIf you have completed all your tasks, make sure to use the "finish" command.\n\n'

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
        # return 'You should only respond in JSON format as described below Response Format:\n{\n"thoughts": {
        # \n"text": "thought",\n"reasoning": "reasoning",\n"plan": "- short bulleted\\n- list that conveys\\n-
        # long-term plan",\n"criticism": "constructive self-criticism",\n"speak": "thoughts summary to say to
        # user"\n},\n"command": {\n"name": "command name",\n"args": {\n"arg name": "value"\n}\n}\n}\nEnsure the
        # response can be parsed by Python json.loads\n'
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
        for event in self.past_events:
            prompt = f"{prompt}\n{event},"
        return f"{date_prompt}This reminds you of these events from your past:\n[{prompt}]\n"

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

    def run(self) -> None:
        openai.organization = "org-bWPRxgvD4e3jFTVqMKVBiGMp"
        load_dotenv()
        openai.api_key = os.getenv("API_KEY")
        command = ""
        while command != "finish":
            print(
                f">Generated prompt:\n{self.get_generated_prompt()}Determine which next command to use, and respond using the "
                "format specified above")
            messages = [{"role": "user",
                         "content": f"{self.get_system_setup_prompt()}{self.get_goals_prompt()}{self.get_constraints_prompt()}{self.get_commands_prompt()}{self.get_resources_prompt()}{self.get_perfeval_prompt()}{self.get_format_prompt()}{self.get_past_events_prompt()}"},
                        {"role": "user", "content": "Determine which next command to use, and respond using the "
                                                    "format specified above"}]
            completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, temperature=0)
            res = completion.choices[0].message.content
            print(f">Assistant Reply: {res}")
            self.past_events.append(res)
            # Using the preferred role context started generating weird results where it would start using not specified commands
            # Uncommented it as it seems perform as per expectations
            messages.append({"role": "assistant", "content": res})
            res_json_dump = json.loads(res)
            command = res_json_dump["command"]["name"]
            if command != "finish":
                time.sleep(20)  # ratelimit
        print("Exiting gracefully")


agent = Agent([Search(), WriteFile(), ReadFile()], ["write a weather report for SF today"])
agent.run()

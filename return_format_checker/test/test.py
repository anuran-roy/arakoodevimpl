from return_format_checker.function import Agent as FunctionalAgent
from return_format_checker.non_function import Agent as NonFunctionalAgent

import json


def test_function():
    with open('prompt.jsonl') as f:
        data = [json.loads(jline) for jline in f.read().splitlines()]
    for line in data:
        fagent = FunctionalAgent(json.loads(json.dumps(line["schema"])), line["query"])
        print(fagent.run())
        nfagent = NonFunctionalAgent(line["schema"], line["query"])
        print(nfagent.run())


test_function()

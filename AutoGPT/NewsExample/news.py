import os

from dotenv import load_dotenv

import AutoGPT.AutoGPT as AutoGPT
from serpapi import GoogleSearch

load_dotenv()


class SearchNews(AutoGPT.Tool):
    def __init__(self) -> None:
        schema = {"query": {"title": "Query", "type": "string"}, "num": {"title": "Number of results", "type": "int"}}
        super().__init__(
            "search_news",
            "useful for when you need to search for news, include the search query under 'query', "
            "limit the number of results by specifying number of results required under 'num'",
            schema,
            self.search
        )

    @staticmethod
    def search(args):
        search = args["query"]
        num = args["num"]
        res = GoogleSearch({
            "q": search,
            "tbm": "nws",
            "num": num,
            "api_key": os.getenv("SERPAPI_API_KEY")
        })
        res = res.get_dict()
        res = res["news_results"]
        return res


memory = AutoGPT.Memory()
agent = AutoGPT.Agent([SearchNews(), AutoGPT.ReadFile(), AutoGPT.WriteFile()],
                      ["Search for 2 world news and generate a summary for the news in a single file seperated by a "
                       "newline with a link to the article at the beginning"],
                      memory)
agent.run()

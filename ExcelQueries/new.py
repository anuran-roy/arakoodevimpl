import subprocess

import pandas as pd


def csv_to_redis():
    df = pd.read_csv('data/data.csv')
    command = "cat data.csv | awk -F',' 'NR>1{{ print \"HSET\", NR, {entry}}}' | redis-cli --pipe"
    entry = ""
    for idx, col in enumerate(df.columns):
        entry += f"\"{col}\", ${idx + 1}"
        if idx < len(df.columns) - 1:
            entry += ", "
    command = command.format(entry=entry)
    print(command)
    res = subprocess.run(f"cd data;{command}", shell=True)


csv_to_redis()

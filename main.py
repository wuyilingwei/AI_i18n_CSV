import logging
import toml
import csv
import json
import requests
import logging
import re

# initialize logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('log.txt')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Load the default config
config = toml.load("config.toml")

# Load [common]
common_config = config.get('common', {})
csvfilename = common_config.get('csvfilename', 'default.csv')
outputfilename = common_config.get('outputfilename', 'output.csv')
logfilename = common_config.get('logfilename', 'log.txt')
Columns = common_config.get('Columns', '1')

# Load [LLM]
llm_config = config.get('LLM', {})
api = llm_config.get('api', 'https://api.openai.com/v1/chat/completions')
apikey = llm_config.get('apikey', 'No API key provided')
model = llm_config.get('model', 'gpt-4o-mini')
lang = llm_config.get('lang', 'en')
prompt = llm_config.get('prompt', 'You are a professional, authentic machine translation engine. Translate text to {lang}, preserving structure, codes, and markup.').replace('{lang}', lang)
isParallelProcessing = llm_config.get('isParallelProcessing', False)
signParallelProcessing = llm_config.get('signParallelProcessing', '||')
promptParallelProcessing = llm_config.get('promptParallelProcessing', 'Separate translations with {signParallelProcessing}.').replace('{signParallelProcessing}', signParallelProcessing)
modelPromptTokensPrice = llm_config.get('modelPromptTokensPrice', 0)
modelCompletionTokensPrice = llm_config.get('modelCompletionTokensPrice', 0)
promptTokens = 0
completionTokens = 0

# Load [connection]
connection_config = config.get('connection', {})
isProxy = connection_config.get('isProxy', False)
address = connection_config.get('address', '')
port = connection_config.get('port', '')
username = connection_config.get('username', '')
password = connection_config.get('password', '')

logger.info("Configuration loaded successfully")
logger.debug(f"Common config: {common_config}")
logger.debug(f"LLM config: {llm_config}")
logger.debug(f"Connection config: {connection_config}")

# Parse a row of the CSV file
def parse_row(rows):
    rows = re.sub(r'\s+', '', rows)
    result = []
    elements = rows.split(',')

    for element in elements:
        if '-' in element:
            try:
                start, end = map(int, element.split('-'))
                if start > end:
                    raise ValueError(f"Invalid range: {element}")
                result.extend(range(start, end + 1))
            except ValueError as e:
                logging.error(f"Error parsing range '{element}': {e}")
        else:
            try:
                result.append(int(element))
            except ValueError as e:
                logging.error(f"Error parsing number '{element}': {e}")
    result.sort()
    for i in range(len(result)):
        result[i] = i - 1
    return result

wishColumns = parse_row(Columns)

# request the API
def requestLLM(text="") -> str:
    if isParallelProcessing:
        sendPrompt = f"{prompt}{promptParallelProcessing}"
    else:
        sendPrompt = prompt

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {apikey}"
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": sendPrompt
            },
            {
                "role": "user",
                "content": text
            }
        ]
    }

    proxies = None
    if isProxy:
        proxies = {
            "http": f"http://{username}:{password}@{address}:{port}",
            "https": f"http://{username}:{password}@{address}:{port}"
        }

    response = requests.post(api, headers=headers, data=json.dumps(data), proxies=proxies)

    global promptTokens, completionTokens
    response_data = response.json()
    if 'usage' in response_data:
        promptTokens += response_data['usage']['prompt_tokens']
        completionTokens += response_data['usage']['completion_tokens']
        logger.debug(f"Prompt tokens: {promptTokens}, Completion tokens: {completionTokens}")
    else:
        logger.warning('No usage data found')

    if response.status_code == 200:
        openai_result = response_data['choices'][0]['message']['content']
        logger.info(f'{text} -> {openai_result}')
        return openai_result
    else:
        logger.error(f"Request failed, status code: {response.status_code}")
        logger.error(headers)
        logger.error(data)
        logger.error(response.text)
        return "Failed"

# Read the CSV file and translate the specified rows
with open(csvfilename, 'r') as file:
    reader = csv.reader(file)
    header = next(reader)
    actualColumns = list(range(len(header)))
    translateColumns = sorted(set(wishColumns).union(actualColumns))

    # Write the header to the output file
    with open(outputfilename, 'w', newline='') as outputfile:
        writer = csv.writer(outputfile)
        writer.writerow(header)

    for row in reader:
        rawRow = row
        if isParallelProcessing:
            text = signParallelProcessing.join([row[i] for i in translateColumns])
            translation = requestLLM(text)
            translations = translation.split(signParallelProcessing)
            for i, col in enumerate(translateColumns):
                if i < len(translations):
                    row[col] = translations[i]
        else:
            for col in translateColumns:
                if col < len(row):
                    text = row[col]
                    translation = requestLLM(text)
                    row[col] = translation
        logger.info(f"Translated row: {rawRow} -> {row}")
        with open(outputfilename, 'a', newline='') as outputfile:
            writer = csv.writer(outputfile)
            writer.writerow(row)

logger.info("Translation completed")
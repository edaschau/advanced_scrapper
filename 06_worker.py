import json
import subprocess
import queue
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

task_queue = queue.Queue()
results = {}
NUM_WORKERS = 3

def main():
    browser_args = json.dumps({
        "headless": False,
        "no_images": True,
        "no_javascript": True,
        "zoom": 0.1,
        "no_autoplay": True,
        "timeout": 30
    })

    workers = {}
    for i in range(NUM_WORKERS):
        print("Initializing worker",i)
        workers[i] = {}
        workers[i]["process"] = subprocess.Popen(['python3', '07_single_worker.py', browser_args],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  text=True)
        workers[i]['busy']= False
        workers[i]['url']= None
        time.sleep(3)

    while True:
        for i in workers:
            if not workers[i]['busy']:
                try:
                    url = task_queue.get_nowait()
                    print(f"START: worker{i},url:{url}")
                    workers[i]['process'].stdin.write(url + '\n')
                    workers[i]['process'].stdin.flush()
                    workers[i]['busy'] = True
                    workers[i]['url'] = url
                except queue.Empty:
                    pass

            if workers[i]['busy']:
                output = workers[i]['process'].stdout.readline().strip()
                if output:
                    print(f"FINISHED: worker{i},url{url}")
                    try:
                        result = json.loads(output)
                        results[workers[i]['url']] = result
                        workers[i]['busy'] = False
                        workers[i]['url'] = None
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON: {output}")

                error = workers[i]['process'].stderr.readline().strip()
                if error:
                    try:
                        error_dict = json.loads(error)
                        results[workers[i]['url']] = {"error": error_dict['error']}
                        workers[i]['busy'] = False
                        workers[i]['url'] = None
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON: {error}")

        time.sleep(0.1)

@app.route('/process_url', methods=['POST'])
def process_url():
    url = request.json['url']
    
    if url in results:
        return jsonify(results[url])
    
    task_queue.put(url)
    
    timeout = 60  # 60 seconds timeout
    start_time = time.time()
    while url not in results:
        time.sleep(0.1)
        if time.time() - start_time > timeout:
            return jsonify({'error': 'Processing timeout', 'url': url}), 408
    
    return jsonify(results[url])

if __name__ == '__main__':
    import threading
    threading.Thread(target=main, daemon=True).start()
    app.run(port=5555)
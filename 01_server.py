import json
import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)


# Vorlagenspeicher
templates = {}


def load_templates():
    print("***LOADING TEMPLATE***")
    global templates
    try:
        with open('templates.json', 'r') as file:
            templates = json.load(file)
    except FileNotFoundError:
        templates = {}


def save_templates():
    print("***SAVING TEMPLATE***")
    with open('templates.json', 'w') as file:
        json.dump(templates, file)


@app.route('/add_template', methods=['POST'])
def add_template():
    print("***ADD TEMPLATE***")
    data = request.get_json()
    template_name = data['name']
    template_data = data['template']
    templates[template_name] = template_data
    save_templates()
    
    # Erstelle einen Ordner für die Vorlage
    os.makedirs(template_name, exist_ok=True)
    
    return jsonify({'message': 'Template added successfully'})


@app.route('/extract_and_get_article', methods=['POST'])
def extract_and_get_article():
    print("***EXTRACT AND GET ARTICLE***")
    data = request.get_json()
    url = data['url']
    template_name = data['template']

    task = {
        'url': url,
        'template': template_name
    }

    # Sende die Aufgabe an den Worker und erhalte das Ergebnis
    worker_response = requests.post('http://localhost:5555/process_url', json=task)
    
    if worker_response.status_code == 200:
        result = worker_response.json()
        
        # Speichere den HTML-Quelltext in einer Datei
        if 'html_source' in result:
            html_source = result.pop('html_source')
            filename = os.path.join(template_name, f"{url.split('/')[-1]}.html")
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(html_source)
        
        return jsonify(result)
    else:
        return jsonify({'message': 'Worker failed to process the request'}), 500


if __name__ == '__main__':
    load_templates()
    app.run(port=5556)



import json
import urllib.request


def walk(items, depth=0):
    for item in items:
        dates = f"{item['start_date']} ~ {item['due_date']}"
        print(f"{'  ' * depth}[{item['status']}] {item['title']} ({dates})")
        walk(item.get("children", []), depth + 1)


data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/work-items").read())
walk(data)

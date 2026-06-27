import urllib.request, json

resp = urllib.request.urlopen('http://127.0.0.1:8765/api/progress')
d = json.loads(resp.read())
s = d['stats']
t = d['tasks']
print(f"Running: {d['running']}")
print(f"Keyword: {d['current_keyword']}")
print(f"Site: {d['current_site']}")
print(f"Novel: {d['current_novel']}")
print(f"Searched: {s['searched']} | Filtered: {s['filtered']} | Downloaded: {s['downloaded']} | Failed: {s['failed']} | Skipped: {s['skipped']}")
print(f"Tasks: total={t['total']} completed={t['completed']} failed={t['failed']} skipped={t['skipped']} downloading={t['downloading']}")

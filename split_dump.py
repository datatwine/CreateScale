import json
import io
with io.open("dump-utf8.json","r",encoding="utf-8") as f:
    data = json.load(f)

no_profiles = [o for o in data if o.get("model") != "users.profile"]
profiles    = [o for o in data if o.get("model") == "users.profile"]

io.open("dump-no-profiles.json","w",encoding="utf-8").write(
    json.dumps(no_profiles, ensure_ascii=False)
)
io.open("dump-profiles.json","w",encoding="utf-8").write(
    json.dumps(profiles, ensure_ascii=False)
)

print("no_profiles:", len(no_profiles), "profiles:", len(profiles))

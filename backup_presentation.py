"""Whitelisted archive descriptions and explicit importer outcome presentation."""
import json

CATEGORIES = {"cases": "cases", "tags": "tags", "actors": "threat_actors", "families": "malware_families", "task_collections":"task_collections"}


def record(category, identifier, name, **fields):
    return dict(category=category, identifier=str(identifier or ""), name=str(name or ""), **fields)


def profile(category, value):
    return record(category, value["id"], value["name"], aliases=value.get("aliases", []),
                  description=value.get("short_description", ""), report_count=len(value.get("reports",[])),
                  reports=[dict(identifier=r["id"],name=r.get("original_filename") or r.get("title") or r["id"]) for r in value.get("reports",[])])


def skipped_profile_details(item):
    reports=item.get('reports',[])
    noun='family' if item['category']=='families' else 'actor'
    names='; '.join(r['name']+' ('+r['identifier']+')' for r in reports)
    return ('Keep destination '+noun+' unchanged; skip incoming '+noun+' "'+item['name']+'" ('+item['identifier']+') and '+str(item.get('report_count',len(reports)))+' attached report(s).'+(' Skipped reports: '+names+'.' if names else ''))


def database_records(source):
    """Read display fields only, never credentials, file paths or private keys."""
    result = []
    fields = {"task_collections":("id","name","description","revision","tasks","origin"),"cases": ("number", "name", "stage", "created"), "tags": ("id", "name"),
              "actors": ("id", "name", "aliases", "short_description"),
              "families": ("id", "name", "aliases", "short_description")}
    for category, table in CATEGORIES.items():
        available = {row[1] for row in source.execute(f'PRAGMA table_info("{table}")')}
        selected = [field for field in fields[category] if field in available]
        if not {"name"}.issubset(selected):
            continue
        for row in source.execute('SELECT ' + ','.join(selected) + f' FROM "{table}"'):
            value = dict(zip(selected, row))
            item = record(category, value.get("number", value.get("id")), value["name"])
            if category=="task_collections":
                item.update(description=value.get("description",""),revision=value.get("revision"),task_count=len(json.loads(value.get("tasks","[]"))),origin=value.get("origin","custom"))
                if item["origin"]=="core":item["details"]="Application-managed Core definition. Bundled upgrades preserve Case snapshots and their recorded source revisions."
            for field in ("stage", "created", "short_description", "aliases"):
                if field in value:
                    item["description" if field == "short_description" else field] = value[field]
            if isinstance(item.get("aliases"), str):
                item["aliases"] = json.loads(item["aliases"])
            item.update(predicted_action="replaced", details="Complete application replacement; destination data will be replaced.")
            result.append(item)
    return result


def case_action(action):
    if action.startswith("Imported"):
        return "added"
    if action.startswith("Updated"):
        return "updated"
    if action.startswith("Replaced"):
        return "replaced"
    if action == "Unchanged":
        return "unchanged"
    if action in ("Kept local", "Skipped older"):
        return "skipped"
    if "conflict" in action.lower():
        return "conflict"
    return "error" if "failed" in action.lower() or "rolled back" in action.lower() else "not_processed"


def outcomes(preview, case_outcomes, shared, *, replaced=False):
    result = []
    cases = {item["index"]: item for item in case_outcomes}
    confirmed = {(item["category"], item["identifier"]): item for item in (shared or [])}
    for original in preview.get("records", []):
        item = dict(original)
        if replaced:
            item.update(action="replaced", details="Restored by completed application replacement.")
        elif item["category"] == "cases":
            outcome = cases.get(item.get("index"))
            item.update(action=case_action(outcome["action"]) if outcome else "not_processed",
                        details=outcome.get("reason") or outcome["action"] if outcome else "No completed record outcome was recorded.")
        else:
            completed = confirmed.get((item["category"], item["identifier"]))
            if completed:
                item.update(completed)
            elif item.get("predicted_action") == "skipped" and shared is not None:
                item.update(action="skipped", details=skipped_profile_details(item) if item["category"] in ("families","actors") else "Skipped by the reviewed keep-destination choice.")
            else:
                item.update(action="not_processed", details="No completed record outcome was recorded.")
        if item.get("action") == "error":
            item["details"] = "Record import failed safely; changes to this record were rolled back. Contact an administrator for diagnostic details."
        item.pop("predicted_action", None)
        result.append(item)
    return result

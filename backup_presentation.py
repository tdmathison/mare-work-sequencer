"""Whitelisted archive descriptions and explicit importer outcome presentation."""
import json

CATEGORIES = {"cases": "cases", "tags": "tags", "actors": "threat_actors", "families": "malware_families", "task_collections":"task_collections"}


def record(category, identifier, name, **fields):
    return dict(category=category, identifier=str(identifier or ""), name=str(name or ""), **fields)


def profile(category, value):
    return record(category, value["id"], value["name"], aliases=value.get("aliases", []),
                  description=value.get("short_description", ""))


def database_records(source):
    """Read display fields only, never credentials, file paths or private keys."""
    result = []
    fields = {"task_collections":("id","name","description","revision","tasks"),"cases": ("number", "name", "stage", "created"), "tags": ("id", "name"),
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
                item.update(description=value.get("description",""),revision=value.get("revision"),task_count=len(json.loads(value.get("tasks","[]"))))
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
                item.update(action="skipped", details="Skipped by the reviewed keep-destination choice.")
            else:
                item.update(action="not_processed", details="No completed record outcome was recorded.")
        if item.get("action") == "error":
            item["details"] = "Record import failed safely; changes to this record were rolled back. Contact an administrator for diagnostic details."
        item.pop("predicted_action", None)
        result.append(item)
    return result

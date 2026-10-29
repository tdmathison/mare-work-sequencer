def run(context):
    print("Hello World", flush=True)
    context.log("Hello World diagnostic")
    return {"ok": True}

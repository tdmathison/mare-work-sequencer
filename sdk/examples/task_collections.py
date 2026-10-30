"""Create guidance and copy it to a Case only when --apply is explicitly supplied."""
import argparse
import uuid
from mws_sdk import MWSClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id',type=int)
    parser.add_argument('--collection-name',required=True)
    parser.add_argument('--task-name',required=True)
    parser.add_argument('--description',default='')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with MWSClient() as client:
        available=client.task_collections.list()
        for collection in available.collections:
            print(collection.id,collection.name,collection.revision,collection.task_count)
        if not args.apply:
            print('Read only. Pass --apply to create this guidance and add it to the Case.')
            return
        created=client.task_collections.create(data={
            'name':args.collection_name,'description':args.description,
            'tasks':[{'name':args.task_name,'description':args.description}],
        }).collection
        result=client.task_collections.apply(args.case_id,created.id,data={
            'revision':created.revision,'template_ids':[task.id for task in created.tasks],
            'mode':'missing','request_key':uuid.uuid4().hex,
        })
        print('Created independent Case group',result.group_id,'with',result.count,'Not Started tasks.')


if __name__=='__main__':main()

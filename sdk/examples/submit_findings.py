"""Explicit write example; requires a case ID and a finding chosen by the caller."""
import argparse
from mws_sdk import MWSClient

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id',type=int)
    parser.add_argument('--finding',required=True)
    parser.add_argument('--apply',action='store_true',help='Required to submit this finding to the real API')
    args=parser.parse_args()
    with MWSClient() as client:
        record=client.cases.get(args.case_id).case
        print(record.number,record.name)
        if args.apply:
            result=client.notes.create(args.case_id,data={'title':'Automation finding','body':args.finding})
            print('Created note',result.note.id)
        else:print('Read only; pass --apply to submit the supplied finding.')

if __name__=='__main__':main()

"""Preview a CSV in an existing section; applying requires an explicit flag."""
import argparse
from pathlib import Path
from mws_sdk import MWSClient

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id',type=int);parser.add_argument('csv',type=Path)
    parser.add_argument('--section',default='default');parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with MWSClient() as client:
        preview=client.indicators.preview_import(args.case_id,data={'section_id':args.section,'format':'csv'},files={'csv':args.csv})
        print('Preview rows:',len(preview.rows),'Revision:',preview.revision)
        accepted=[row['row'] for row in preview.rows if not row.get('reason') and not row.get('duplicate')]
        if args.apply:
            result=client.indicators.import_rows(args.case_id,data={'revision':preview.revision,'section_id':args.section,'accepted_rows':accepted})
            print('Added',result.added)
        else:print('Preview only; inspect the results before using --apply.')

if __name__=='__main__':main()

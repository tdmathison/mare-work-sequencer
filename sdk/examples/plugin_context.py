"""External-plugin pattern: REST context and coverage, without a plugin runtime."""
import argparse
from mws_sdk import MWSClient

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('case_id',type=int);args=parser.parse_args()
    with MWSClient() as client:
        case=client.cases.get(args.case_id).case
        indicators=client.indicators.get(case.id)
        print(case.number,'indicator sections:',len(indicators.sections))
        print(client.coverage.get(params={'scope':'all','q':case.number}).rows)

if __name__=='__main__':main()

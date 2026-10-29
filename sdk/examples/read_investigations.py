"""Read-only example. Credentials: MWS_BASE_URL and MWS_API_KEY."""
from mws_sdk import MWSClient, MWSError

def main():
    try:
        with MWSClient() as client:
            for case in client.cases.iter_all(params={'limit':50,'sort':'number'}):
                print(case.number,case.name,case.stage_name)
            result=client.coverage.get(params={'scope':'all','missing':'1'})
            print(result.note)
            for gap in result.gaps:print(gap.kind,gap.name,gap.suggestion)
    except MWSError as error:
        print(type(error).__name__,error.status_code,str(error))

if __name__=='__main__':main()

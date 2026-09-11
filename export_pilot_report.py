"""Export explicitly public readiness fields; never copies vaults or endpoints."""
import json
from pilot_runtime import Journal, STATE, ROOT
from pilot_chain import preflight
from pilot_wallets import Wallets

def export():
    check=preflight(Wallets().public())
    (STATE/'preflight.json').write_text(json.dumps(check,indent=2))
    journal=Journal();state=journal.load();journal.db.close()
    report={'runtime':'saved_neural_paper_report','running':False,'busy':False,'error':None,'state':state,'preflight':check}
    (ROOT/'dist/pilot-status.json').write_text(json.dumps(report,indent=2))
    print('Saved paper pilot report. No credentials or control token exported.')

if __name__=='__main__':export()

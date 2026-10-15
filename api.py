"""Local sandbox adapter. Never expose publicly without enterprise security review."""
import base64
import binascii
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from inspector import inspect

app=FastAPI(title='Demo Workato DLP Inspector',docs_url=None,redoc_url=None)
class InspectionInput(BaseModel):
    file_name: str = Field(min_length=1,max_length=200)
    file_base64: str = Field(min_length=1,max_length=7500000)
    request_id: str = Field(default='workato',max_length=100)

@app.post('/inspect')
def inspect_endpoint(payload:InspectionInput, x_inspector_token: str | None = Header(default=None)):
    secret=os.environ.get('INSPECTOR_TOKEN')
    if not secret or x_inspector_token != secret:
        raise HTTPException(status_code=401, detail='unauthorized')
    try:
        data=base64.b64decode(payload.file_base64,validate=True)
    except (binascii.Error,ValueError):
        return {'decision':'BLOCK','file_name':payload.file_name,'policy_version':'DEMO-1.0',
                'reason_code':'INVALID_BASE64','request_id':payload.request_id}
    return inspect(payload.file_name,data,payload.request_id)

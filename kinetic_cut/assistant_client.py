"""Dependency-free local MCP client for diagnostics and development tools."""
import json
import urllib.request


class Client:
    def __init__(self,url,token):self.url=url; self.token=token; self.sequence=0
    def request(self,method,params=None):
        self.sequence+=1
        data=json.dumps(dict(jsonrpc='2.0',id=self.sequence,method=method,params=params or {})).encode()
        request=urllib.request.Request(self.url,data=data,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'})
        with urllib.request.urlopen(request,timeout=20) as response:result=json.loads(response.read())
        if 'error' in result:raise RuntimeError(result['error']['message'])
        return result['result']
    def initialize(self,name='Kinetic Cut diagnostic client'):
        return self.request('initialize',dict(protocolVersion='2025-06-18',clientInfo=dict(name=name,version='1.0'),capabilities={}))
    def call(self,name,**arguments):
        result=self.request('tools/call',dict(name=name,arguments=arguments))
        if result.get('isError'):raise RuntimeError(result['content'][0]['text'])
        return result
    def value(self,name,**arguments):return json.loads(self.call(name,**arguments)['content'][0]['text'])

import io,json,unittest
from worker.dispatch_next import dispatch_next

class Response(io.BytesIO):
    status=204

class ContinuationTests(unittest.TestCase):
    def test_uses_normal_budget_only_after_native_pause_is_verified(self):
        calls=[]
        def open_request(request,**kwargs):
            calls.append(request)
            return Response(json.dumps({'protection_rules':[{'type':'wait_timer','wait_timer':15}]}).encode()) if len(calls)==1 else Response()
        dispatch_next('temporary-token','htceGit/orbita-milhas','refs/heads/main',open_request)
        self.assertEqual(json.loads(calls[-1].data),{'ref':'main','inputs':{'query_limit':'0','mode':'scan','trigger_source':'continuation'}})
        self.assertEqual(len(calls),2)
    def test_missing_timer_prevents_a_runaway_loop(self):
        calls=[]
        def open_request(request,**kwargs):calls.append(request);return Response(b'{"protection_rules":[]}')
        with self.assertRaises(RuntimeError):dispatch_next('token','htceGit/orbita-milhas','refs/heads/main',open_request)
        self.assertEqual(len(calls),1)
    def test_other_repository_or_branch_cannot_dispatch(self):
        for repository,ref in [('other/repo','refs/heads/main'),('htceGit/orbita-milhas','refs/heads/other')]:
            with self.assertRaises(ValueError):dispatch_next('token',repository,ref)

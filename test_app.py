import unittest
from unittest.mock import patch
import app
class Tests(unittest.TestCase):
    def test_reject(self):
        for u in ['file:///etc/passwd','http://a.com:22','http://user@a.com','http://localhost','http://a.com\\@b.com','https://a.com/\n']:
            with self.subTest(u=u), self.assertRaises(app.LinkError): app.parse_url(u)
    @patch('app.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',80))])
    def test_private(self,_):
        with self.assertRaises(app.LinkError): app.public_ip('example.com',80)
    @patch('app.response_headers',side_effect=[(302,'https://example.org/final'),(200,None)])
    def test_redirect(self,_): self.assertEqual(app.resolve_redirect('https://example.com/a')['url'],'https://example.org/final')
    @patch('app.response_headers',return_value=(200,None))
    def test_no_false_success(self,_): self.assertEqual(app.resolve_redirect('https://example.com/a')['status'],'manual')
    @patch('app.response_headers',return_value=(302,'/a'))
    def test_loop(self,_):
        with self.assertRaises(app.LinkError): app.resolve_redirect('https://example.com/a')
    @patch('app.response_headers',return_value=(302,'file:///etc/passwd'))
    def test_unsafe_hop(self,_):
        with self.assertRaises(app.LinkError): app.resolve_redirect('https://example.com/a')
class RouteTests(unittest.TestCase):
    def test_home_and_query(self):
        import threading, http.client
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            for method,path,expected in [('GET','/',200),('GET','/?utm_source=chatgpt.com',200),('GET','/index.html',200),('GET','/api/config?v=1',200),('HEAD','/',200),('GET','/missing',404)]:
                with self.subTest(method=method,path=path):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                    try:
                        conn.request(method,path)
                        res=conn.getresponse()
                        self.assertEqual(res.status,expected)
                        body=res.read()
                        if method=='HEAD': self.assertEqual(body,b'')
                        elif path in ('/','/?utm_source=chatgpt.com','/index.html'): self.assertIn(b'Link All-in-One',body)
                    finally: conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

class AutoTests(unittest.TestCase):
    def test_refresh(self):
        self.assertEqual(app.refresh_target("0; URL='https://example.org/a'"),'https://example.org/a')
        self.assertIsNone(app.refresh_target('hello'))
        parser=app.RefreshParser()
        parser.feed('<meta http-equiv="refresh" content="0;url=/next">')
        self.assertEqual(parser.destination,'/next')
    def test_platform(self):
        self.assertEqual(app.platform('https://toplinks.io/a'),'TopLinks')
        self.assertEqual(app.platform('https://toplinks.io.example.com/a'),'toplinks.io.example.com')
    @patch('app.crowd_lookup')
    @patch('app.response_headers',return_value=(403,None))
    def test_opt_in(self,_,lookup):
        self.assertEqual(app.resolve_auto('https://toplinks.io/a')['status'],'manual')
        lookup.assert_not_called()
        lookup.return_value={'status':'candidate','url':'https://example.org/a'}
        self.assertEqual(app.resolve_auto('https://toplinks.io/a',True)['status'],'candidate')
    @patch('app.public_ip')
    def test_private_query_not_shared(self,ip):
        self.assertIsNone(app.crowd_lookup('https://example.com/a?token=secret'))
        ip.assert_not_called()
if __name__=='__main__': unittest.main()

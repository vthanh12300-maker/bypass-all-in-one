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
if __name__=='__main__': unittest.main()

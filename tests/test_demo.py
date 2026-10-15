import unittest
from pathlib import Path
from sys import path
path.insert(0,str(Path(__file__).resolve().parents[1]))
from inspector import inspect
ROOT=Path(__file__).resolve().parents[1]/'samples'
class Tests(unittest.TestCase):
    def check(self,name,expected):
        r=inspect(name,(ROOT/name).read_bytes());self.assertEqual(r['decision'],expected, r)
    def test_public_text(self): self.check('public.txt','ALLOW')
    def test_restricted_csv(self): self.check('restricted.csv','BLOCK')
    def test_public_pdf(self): self.check('public.pdf','ALLOW')
    def test_secret_docx(self): self.check('restricted.docx','BLOCK')
    def test_secret_xlsx(self): self.check('restricted.xlsx','BLOCK')
    def test_public_pptx(self): self.check('public.pptx','ALLOW')
    def test_public_json(self): self.check('public.json','ALLOW')
    def test_image_fails_closed(self): self.check('public.png','BLOCK')
    def test_spoof_fails_closed(self): self.assertEqual(inspect('fake.pdf',b'hello')['decision'],'BLOCK')
if __name__=='__main__': unittest.main()

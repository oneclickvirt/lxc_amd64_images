import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import published_image_suite as suite

class PublishedImageSelectionTests(unittest.TestCase):
    def selection(self, image):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'output'
            environment={'GITHUB_REPOSITORY':'oneclickvirt/lxc_amd64_images',
                         'GH_TOKEN':'fixture', 'GITHUB_OUTPUT':str(output),'IMAGE':image}
            assets=[{'name':'openeuler_24.03_24.03_x86_64_default.tar.xz','tag':'openeuler'},
                    {'name':'debian_12_bookworm_x86_64_default.tar.xz','tag':'debian'}]
            with mock.patch.dict(os.environ,environment), mock.patch.object(sys,'argv',['suite','matrix']), \
                 mock.patch.object(suite,'Publisher'), mock.patch.object(suite,'published',return_value=assets):
                suite.main()
            return json.loads(output.read_text().removeprefix('matrix='))['include']

    def test_exact_request_does_not_expand_to_smoke_or_full_catalog(self):
        image='openeuler_24.03_24.03_x86_64_default.tar.xz'
        rows=self.selection(image)
        self.assertEqual([row['image'] for row in rows],[image])

    def test_unknown_request_fails_instead_of_testing_unrelated_assets(self):
        with self.assertRaisesRegex(ValueError,'no published images selected'):
            self.selection('missing-image.tar.xz')

if __name__=='__main__': unittest.main()

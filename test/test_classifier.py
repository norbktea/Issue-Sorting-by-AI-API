import os
import unittest
# 雖然連不到 AI，但我們可以測試本地讀取功能是否正常
from main import extract_text_pure_python

class TestIssueClassifier(unittest.TestCase):
    def test_file_not_found(self):
        """測試：當選取不存在的檔案時，是否會正確回傳錯誤訊息"""
        result = extract_text_pure_python("non_existent_file.pdf")
        self.assertTrue("[檔案讀取錯誤]" in result)

if __name__ == "__main__":
    unittest.main()

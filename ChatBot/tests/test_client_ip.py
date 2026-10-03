"""분당 횟수 제한을 사람마다 센다 — 버셀 중계가 넘기는 손님 IP (2026-10-02).

기수 30명 동시 테스트에서 nginx 가 X-Forwarded-For 를 버셀 함수 IP 로 덮어써,
전원이 IP 몇 개로 묶여 분당 20회 제한을 같이 나눠 썼다.
"""
import unittest
from unittest.mock import patch

import server


def handler(headers, peer="10.0.0.9"):
    h = server.Handler.__new__(server.Handler)
    h.headers = headers
    h.client_address = (peer, 5555)
    return h


class ClientIpTests(unittest.TestCase):
    def test_relayed_ip_is_trusted_only_with_the_shared_token(self):
        with patch.object(server, "CHAT_TOKEN", "s3cret"):
            ok = handler({"X-FEEDiT-Token": "s3cret", "X-FEEDiT-Client-IP": "211.36.1.2",
                          "X-Forwarded-For": "76.76.21.21"})
            self.assertEqual(ok._client_ip(), "211.36.1.2")
            forged = handler({"X-FEEDiT-Client-IP": "1.2.3.4", "X-Forwarded-For": "76.76.21.21"})
            self.assertEqual(forged._client_ip(), "76.76.21.21")
            wrong = handler({"X-FEEDiT-Token": "nope", "X-FEEDiT-Client-IP": "1.2.3.4"})
            self.assertEqual(wrong._client_ip(), "10.0.0.9")
            junk = handler({"X-FEEDiT-Token": "s3cret", "X-FEEDiT-Client-IP": "<script>"})
            self.assertEqual(junk._client_ip(), "10.0.0.9")

    def test_without_a_token_the_header_is_ignored(self):
        with patch.object(server, "CHAT_TOKEN", ""):
            h = handler({"X-FEEDiT-Client-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8, 9.9.9.9"})
            self.assertEqual(h._client_ip(), "5.6.7.8")


if __name__ == "__main__":
    unittest.main()

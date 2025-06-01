import requests
from lxml import etree


class IdsAuth:
    cookies = {}
    ok = False

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/106.0.0.0 Safari/537.36',
    }
    s = requests.Session()
    rVerify = False  # 修改为False以禁用SSL证书验证

    def __init__(self, cookies=None):
        if cookies:
            self.s.cookies = requests.utils.cookiejar_from_dict(cookies)
            self.cookies = self.s.cookies.get_dict()
            self.check()
        # 禁用SSL验证警告
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def login(self, username: str, password: str, service: str):
        url = 'https://ids.shiep.edu.cn/authserver/login'

        resp = self.s.get(url,
                          params={'service': service},
                          headers=self.headers,
                          verify=self.rVerify)
        e = etree.HTML(resp.text)
        form = {
            i.get('name'): i.get('value')
            for i in e.xpath('//form//input')
        }
        form['username'] = username
        form['password'] = password

        resp = self.s.post(url,
                           params={'service': service},
                           data=form,
                           headers=self.headers,
                           verify=self.rVerify)
        self.cookies = self.s.cookies.get_dict()
        self.check()

    def check(self):
        url = 'https://jw.shiep.edu.cn/eams/home.action'
        resp = self.s.get(url,
                          headers=self.headers,
                          verify=self.rVerify,
                          allow_redirects=False)
        self.ok = (resp.status_code == 200)

    def get(self, url: str, **kwargs):
        return self.s.get(url, verify=self.rVerify, **kwargs)

    def post(self, url: str, **kwargs):
        return self.s.post(url, verify=self.rVerify, **kwargs)

    def head(self, url: str, **kwargs):
        return self.s.head(url, verify=self.rVerify, **kwargs)

import json
import _jsonnet
import os
import pandas as pd
import threading
from lxml import etree
from time import sleep
from ids import IdsAuth
from envconfig import username, password
from envconfig import skip_course_list, check_course_availability, sheet_format
from envconfig import default_election_id, default_courses_exps
from envconfig import interval, threads_interval

headers = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/106.0.0.0 Safari/537.36',
}

host = 'https://jw.shiep.edu.cn'


def get_elections() -> dict:
    '''Find all available election profile {names:ids}'''
    resp = ids.get(f'{host}/eams/stdElectCourse.action', headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get election profile ids.')
    e = etree.HTML(resp.text)
    election_names = e.xpath(
        '//body/div[@class="ajax_container"]/div/h2/text()')
    election_urls = e.xpath(
        '//body/div[@class="ajax_container"]/div/div/a/@href')
    election_ids = [
        i.split('?')[-1].replace('electionProfile.id=', '')
        for i in election_urls
    ]
    if len(election_names) != len(election_ids):
        raise Exception('Election names and ids do not match.')
    return dict(zip(election_names, election_ids))


def get_courses(election_id: str) -> list:
    '''Get the course list'''
    resp = ids.get(f'{host}/eams/stdElectCourse!data.action',
                   params={'profileId': election_id},
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get course list.')
    data = resp.text  # format: javascript code
    data = data[data.find('['):data.rfind(']') + 1]  # js object
    return json.loads(_jsonnet.evaluate_snippet('snippet', data))


def get_semester_info(election_id: str) -> dict:
    '''Get semester info'''
    resp = ids.get(f'{host}/eams/stdElectCourse!defaultPage.action',
                   params={'electionProfile.id': election_id},
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get semester info.')
    e = etree.HTML(resp.text)
    qr_script_url = e.xpath('//*[@id="qr_script"]/@src')
    if len(qr_script_url) == 0:
        raise Exception('Failed to get semester info.')
    params = {
        i.split('=')[0]: i.split('=')[1]
        for i in qr_script_url[0].split('?')[-1].split('&')
    }
    return params


def get_courses_status(params: dict) -> dict:
    '''Get courses status'''
    resp = ids.get(f'{host}/eams/stdElectCourse!queryStdCount.action',
                   params=params,
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get course status.')
    data = resp.text  # format: javascript code
    data = data[data.find('{'):data.rfind('}') + 1]  # js object
    return json.loads(_jsonnet.evaluate_snippet('snippet', data))


def elect_course(course_id: str, election_id: str) -> list:
    '''Elect a course
    return: [course_id, message, succeeded?, retry?]
    '''
    headers['X-Requested-With'] = 'XMLHttpRequest'
    resp = ids.post(f'{host}/eams/stdElectCourse!batchOperator.action',
                    params={'profileId': election_id},
                    headers=headers,
                    data={
                        'optype': 'true',
                        'operator0': f'{course_id}:true:0'
                    })

    if '会话已经被过期' in resp.text:
        ids.login(username, password, service)
        return [course_id, '会话已经被过期', False, True]

    if resp.status_code != 200:
        if str(resp.status_code).startswith('4'):
            raise Exception('Failed to elect course.', resp.status_code)
        else:
            return [course_id, str(resp.status_code), False, True]

    e = etree.HTML(resp.text)
    msgs = e.xpath('//table/tr[1]/td/div/text()')
    msg = msgs[0].strip() if len(msgs) > 0 else resp.text
    simplified_msgs = [
        '请不要过快点击',
        '服务器内部错误',
    ]
    for simplified_msg in simplified_msgs:
        if simplified_msg in msg:
            msg = simplified_msg
    if '已经选过' in msg:
        return [course_id, msg, True, False]
    failed_words = ['上限', '已满', '已达', '已经达到', '冲突']
    error_words = ['失败', '错误', 'fail', 'error', '503', '过快点击'] + failed_words
    succeeded = not any(i in msg for i in error_words)
    retry = not (any(i in msg for i in failed_words) or succeeded)
    return [course_id, msg, succeeded, retry]


def parse_courses_exp(exp: str, election_id: str) -> list:
    if ';' in exp:
        return [parse_courses_exp(i, election_id) for i in exp.split(';')]
    if '|' in exp:
        for i in exp.split('|'):
            expr, msg, succeeded, retry = parse_courses_exp(i, election_id)
            if succeeded:
                return expr, msg, succeeded, retry
        return exp, msg, succeeded, retry
    if '&' in exp:
        for i in exp.split('&'):
            expr, msg, succeeded, retry = parse_courses_exp(i, election_id)
            if not succeeded:
                return expr, msg, succeeded, retry
        return exp, msg, succeeded, retry

    retry = True
    while retry:
        expr, msg, succeeded, retry = elect_course(exp, election_id)
        print(f'{expr}: {msg} (succeeded:{succeeded}, retry:{retry})')
        sleep(interval)
    return elect_course(exp, election_id)


if __name__ == '__main__':
    ids = IdsAuth()
    service = 'http://jw.shiep.edu.cn/eams/login.action'

    if os.path.exists('cookies.json'):
        with open('cookies.json', 'r') as f:
            cookies = json.load(f)
        ids = IdsAuth(cookies)

    if not ids.ok:
        print('Logging in by username and password...')
        ids.login(username, password, service)

    if ids.ok:
        with open('cookies.json', 'w') as f:
            json.dump(ids.cookies, f)
        print('Login success.')
    else:
        print('Login failed.')
        exit(1)

    elections = get_elections()
    print('Available elections: ')
    for name, id in elections.items():
        print(f'  {name}: {id}')

    if len(elections) == 0:
        print('No available elections.')
        exit(0)
    elif len(elections) == 1:
        election_id = list(elections.values())[0]
    else:
        if default_election_id in elections.values():
            election_id = default_election_id
        else:
            election_id = input('Please select an election id: ')
    print(f'Selected {election_id}.')

    if not check_course_availability:
        ids.get(
            'https://jw.shiep.edu.cn/eams/stdElectCourse!defaultPage.action',
            params={'electionProfile.id': election_id},
            headers=headers)  # Do not remove this

    if not skip_course_list:
        data = get_courses(election_id)

        if check_course_availability:
            params = get_semester_info(election_id)
            courses_status = get_courses_status(params)
            for course in data:
                course['available'] = (courses_status[str(course['id'])]['sc']
                                       < courses_status[str(
                                           course['id'])]['lc'])

        if sheet_format == 'tsv':
            df = pd.DataFrame(data)
            filename = f'{election_id}.tsv'
            df.to_csv(filename, sep='\t', index=False)
        elif sheet_format == 'xlsx':
            df = pd.DataFrame(data)
            filename = f'{election_id}.xlsx'
            df.to_excel(filename, index=False)
        else:
            filename = ''

        if check_course_availability:
            data.sort(key=lambda x: (not x['available'], x['id']))
        else:
            data.sort(key=lambda x: x['id'])

        print(f'Please checkout full information on website' +
              '.' if filename == '' else f' or in {filename}.')
        print('Courses: ')
        column_names = ['ID:', 'No.', 'Name', 'Teachers']
        column_keys = ['id', 'no', 'name', 'teachers']
        if check_course_availability:
            column_names.append('Available')
            column_keys.append('available')

        print('  ' + '\t'.join(column_names))
        for course in data:
            print('  ' + '\t'.join([str(course[key]) for key in column_keys]))

    if len(default_courses_exps) == 0:
        print('Please input the courses expressions you want to elect, '
              'end with an empty line.')
        courses_exps = []
        while True:
            courses_exp = input('Courses expression: ')
            if courses_exp == '':
                break
            courses_exps.append(courses_exp)
    else:
        courses_exps = default_courses_exps

    threads = []
    for courses_exp in courses_exps:
        courses_exp = courses_exp.strip().replace(' ', '')
        courses_exp = courses_exp.replace('&&', '&').replace('||', '|')

        t = threading.Thread(target=parse_courses_exp,
                             args=(courses_exp, election_id))
        threads.append(t)
        t.start()
        sleep(threads_interval)

    for t in threads:
        t.join()

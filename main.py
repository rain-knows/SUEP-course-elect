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
from envconfig import default_courses_exps
from envconfig import interval, threads_interval
# 新增导入
from envconfig import ENABLE_RETRY_ON_PERCENTAGE_LIMIT, RETRY_IF_COURSE_FULL_PERCENTAGE_THRESHOLD

# 全局请求头
headers = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/106.0.0.0 Safari/537.36',
}

# 教务系统主机和登录服务地址
host = 'https://jw.shiep.edu.cn'
service = 'http://jw.shiep.edu.cn/eams/login.action'


def get_elections() -> dict[str, str]:
    '''获取所有可选的选课轮次（选课批次）。

    通过访问教务系统的特定页面，解析HTML内容，提取选课轮次的名称和对应的ID。

    Returns:
        dict[str, str]: 一个字典，键是选课轮次的名称，值是选课轮次的ID。
                        例如: {'2023-2024学年第一学期选课': '1655'}

    Raises:
        Exception: 如果获取选课轮次信息失败（例如，网络请求失败或返回状态码非200）。
        Exception: 如果解析到的选课轮次名称数量和ID数量不匹配。
    '''
    resp = ids.get(f'{host}/eams/stdElectCourse!innerIndex.action?projectId=1',
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get election profile ids.')
    e = etree.HTML(resp.text)
    # 使用XPath提取选课轮次的名称
    election_names = e.xpath(
        '//body/div[@class="ajax_container"]/div/h2/text()')
    # 使用XPath提取选课轮次的URL，后续将从中解析出ID
    election_urls = e.xpath(
        '//body/div[@class="ajax_container"]/div/div/a/@href')
    # 从URL中解析选课轮次的ID
    election_ids = [
        i.split('?')[-1].replace('electionProfile.id=', '')  # 提取URL参数中的electionProfile.id
        for i in election_urls
    ]
    if len(election_names) != len(election_ids):
        raise Exception('Election names and ids do not match: '
                        f'{election_names} != {election_ids}')
    return dict(zip(election_names, election_ids))


def get_courses(e_id: str) -> list[dict]:
    '''获取指定选课轮次下的课程列表。

    Args:
        e_id (str): 选课轮次的ID。

    Returns:
        list[dict]: 包含课程信息的字典列表。每个字典代表一门课程。
                     课程信息通常包含课程ID、名称、教师、学分等。

    Raises:
        Exception: 如果获取课程列表失败（例如，网络请求失败或返回状态码非200）。
    '''
    resp = ids.get(f'{host}/eams/stdElectCourse!data.action',
                   params={'profileId': e_id},
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get course list.')
    dat = resp.text  # 响应内容是包含课程数据的JavaScript代码片段
    # 从JavaScript代码片段中提取JSON数组部分
    dat = dat[dat.find('['):dat.rfind(']') + 1]
    # 使用_jsonnet解析JavaScript对象表示的课程数据
    return json.loads(_jsonnet.evaluate_snippet('snippet', dat))


def get_semester_info(e_id: str) -> dict:
    '''获取指定选课轮次的学期信息。

    这些信息通常用于后续查询课程状态（如已选人数、课容量）。

    Args:
        e_id (str): 选课轮次的ID。

    Returns:
        dict: 包含学期相关参数的字典，例如学期ID、学生ID等。

    Raises:
        Exception: 如果获取学期信息失败。
    '''
    resp = ids.get(f'{host}/eams/stdElectCourse!defaultPage.action',
                   params={'electionProfile.id': e_id},
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get semester info.')
    e = etree.HTML(resp.text)
    # 查找包含学期信息的脚本URL
    qr_script_url = e.xpath('//*[@id="qr_script"]/@src')
    if len(qr_script_url) == 0:
        raise Exception('Failed to get semester info.')
    # 从脚本URL的查询参数中解析学期信息
    params = {
        i.split('=')[0]: i.split('=')[1]
        for i in qr_script_url[0].split('?')[-1].split('&')
    }
    return params


def get_courses_status(params: dict) -> dict:
    '''获取课程的已选人数和课容量等状态信息。

    Args:
        params (dict): 包含查询所需参数的字典，通常来自 `get_semester_info` 的返回结果。

    Returns:
        dict: 包含课程状态信息的字典，键是课程ID，值是包含已选人数('sc')和课容量('lc')的字典。

    Raises:
        Exception: 如果获取课程状态信息失败。
    '''
    resp = ids.get(f'{host}/eams/stdElectCourse!queryStdCount.action',
                   params=params,
                   headers=headers)
    if resp.status_code != 200:
        raise Exception('Failed to get course status.')
    dat = resp.text  # 响应内容是包含课程状态的JavaScript代码片段
    # 从JavaScript代码片段中提取JSON对象部分
    dat = dat[dat.find('{'):dat.rfind('}') + 1]
    # 使用_jsonnet解析JavaScript对象表示的课程状态数据
    return json.loads(_jsonnet.evaluate_snippet('snippet', dat))


def head_election(e_id: str):
    '''发送HEAD请求到选课相关页面。

    这可能用于“预热”会话或模拟用户访问行为，确保后续操作的顺利进行。

    Args:
        e_id (str): 选课轮次的ID。
    '''
    ids.head(f'{host}/eams/stdElectCourse!innerIndex.action?projectId=1',
             headers=headers)
    ids.head(f'{host}/eams/stdElectCourse!defaultPage.action',
             params={'electionProfile.id': e_id},
             headers=headers)


def elect_course(course_id: str, e_id: str, courses_status_data: dict | None = None) -> list:
    '''执行单个课程的选课操作。

    Args:
        course_id (str): 要选择的课程的ID。
        e_id (str): 当前选课轮次的ID。
        courses_status_data (dict | None, optional): 当前选课轮次所有课程的状态数据。
                                                     如果提供了此数据并且启用了相关功能，
                                                     则在课程满员时会根据百分比决定是否重试。
                                                     Defaults to None.

    Returns:
        list: 包含选课结果信息的列表：
              - course_id (str): 尝试选课的课程ID。
              - message (str): 选课操作返回的消息。
              - succeeded (bool): 选课是否成功。
              - retry (bool): 是否需要重试该课程。
    
    Raises:
        Exception: 如果发生客户端错误（如4xx状态码），表明请求本身有问题。
                   对于服务器端错误或可重试的错误，会通过返回值的 `retry` 标志来处理。
    '''
    # 选课请求通常需要这个特殊的请求头
    headers_with_ajax = headers.copy()
    headers_with_ajax['X-Requested-With'] = 'XMLHttpRequest'
    resp = ids.post(f'{host}/eams/stdElectCourse!batchOperator.action',
                    params={'profileId': e_id},
                    headers=headers_with_ajax, # 使用包含 AJAX 标志的请求头
                    data={
                        'optype': 'true',  # 操作类型，true表示选课
                        'operator0': f'{course_id}:true:0'  # 选课参数格式：课程ID:true:0
                    },
                    allow_redirects=False) # 选课操作通常不应发生重定向

    # 处理会话过期的情况
    if '会话已经被过期' in resp.text:
        print("会话过期，尝试重新登录...")
        ids.login(username, password, service) # 重新登录
        return [course_id, '会话已经被过期', False, True] # 返回并标记需要重试

    # 处理非200状态码
    if resp.status_code != 200:
        if str(resp.status_code).startswith('4'): # 客户端错误，通常不可重试
            raise Exception(f'Failed to elect course {course_id}. Status: {resp.status_code}. Response: {resp.text}')
        else: # 其他错误（如服务器5xx错误），可能可以重试
            return [course_id, f'Server error: {str(resp.status_code)}', False, True]

    # 解析选课结果消息
    e = etree.HTML(resp.text)
    msgs = e.xpath('//table/tr[1]/td/div/text()') # 尝试从特定路径提取消息
    msg = msgs[0].strip() if len(msgs) > 0 else resp.text # 如果路径找不到，使用完整响应文本

    # 简化常见的提示信息
    simplified_msgs = [
        '请不要过快点击',
        '服务器内部错误',
    ]
    for simplified_msg in simplified_msgs:
        if simplified_msg in msg:
            msg = simplified_msg
            break # 一旦匹配到简化消息，就使用它

    # 判断选课是否成功以及是否需要重试
    if '已经选过' in msg or '已选上' in msg: # 明确成功的标志
        return [course_id, msg, True, False]

    # --- 开始重构succeeded和retry的判断逻辑 ---
    course_fullness_keywords = ['上限', '已满', '已达', '已经达到']
    hard_fail_keywords = ['冲突'] # 例如选课时间冲突等，通常不可通过重试解决
    general_error_keywords = ['失败', '错误', 'fail', 'error', '503', '过快点击', '服务器内部错误'] # 其他可能重试的错误

    # 检查消息中是否包含任何负面关键词
    all_negative_keywords = course_fullness_keywords + hard_fail_keywords + general_error_keywords
    
    # 如果消息中不包含任何已知的负面关键词，我们可能认为它是成功的（或者至少不是明确的失败）
    # 注意：原始逻辑是只要没有error_words就succeeded=True。这里保持类似行为。
    # 如果msg是空或者未知信息，且不含error words，则succeeded为True。
    succeeded = not any(keyword in msg for keyword in all_negative_keywords)

    if succeeded:
        # 如果根据关键词判断没有发生错误/满员/冲突，则认为操作成功，不需重试。
        # 这也覆盖了那些非明确成功提示（如“已选上”）但也没有错误的操作。
        return [course_id, msg, True, False]

    # 至此，succeeded 为 False，意味着消息中包含某种负面关键词。
    # 现在决定是否需要重试。默认对于失败情况不重试，除非特定逻辑允许。
    retry = False

    is_course_full_msg = any(fw in msg for fw in course_fullness_keywords)

    if is_course_full_msg:
        # 检测到课程已满相关的消息
        if ENABLE_RETRY_ON_PERCENTAGE_LIMIT and courses_status_data is not None:
            course_specific_status = courses_status_data.get(str(course_id))
            if course_specific_status:
                sc = course_specific_status.get('sc', 0)  # selected count
                lc = course_specific_status.get('lc', 0)  # limit capacity
                if lc > 0: # 避免除以零
                    current_percentage = (float(sc) / lc) * 100
                    # 修改这里的条件，从 < 改为 <=
                    if current_percentage <= RETRY_IF_COURSE_FULL_PERCENTAGE_THRESHOLD:
                        print(f"[Info] Course {course_id} full ({current_percentage:.2f}%), but at or below threshold {RETRY_IF_COURSE_FULL_PERCENTAGE_THRESHOLD}%. Retrying.")
                        retry = True # 等于或低于阈值，重试
                    else:
                        print(f"[Info] Course {course_id} full ({current_percentage:.2f}%) and above threshold {RETRY_IF_COURSE_FULL_PERCENTAGE_THRESHOLD}%. Not retrying for fullness.")
                        retry = False # 超过阈值，不因满员而重试
                else:
                    # 课容量为0或无效，对于满员消息不重试
                    retry = False
            else:
                # 未找到该课程的状态信息，对于满员消息不重试
                print(f"[Warning] Course status for {course_id} not found for percentage check. Not retrying for fullness.")
                retry = False
        else:
            # 百分比重试功能未启用或课程状态数据未提供，对于满员消息不重试
            retry = False
    elif any(hfk in msg for hfk in hard_fail_keywords):
        # 是硬性失败（如“冲突”），不重试
        retry = False
    elif any(gek in msg for gek in general_error_keywords):
        # 是其他一般性错误（如“服务器内部错误”，“过快点击”），这些通常是可重试的
        retry = True
    # 如果消息不匹配任何已知模式，但之前被判断为succeeded=False，默认retry=False

    return [course_id, msg, succeeded, retry]
    # --- 结束succeeded和retry的判断逻辑 ---


def parse_courses_exp(exp: str, e_id: str, original_exp_for_thread: str, courses_status_data: dict | None) -> list:
    '''解析并执行课程选择表达式。

    表达式支持以下操作符：
    - ';' (分号): 顺序执行，无论前一个是否成功，都会执行下一个。返回最后一个操作的结果。
    - '|' (竖线): 或操作，从左到右尝试，一旦成功则停止并返回成功结果。如果都失败，返回最后一个的失败结果。
    - '&' (与号): 与操作，从左到右尝试，一旦失败则停止并返回失败结果。如果都成功，返回最后一个的成功结果。
    单个课程ID会直接尝试选课，并根据结果进行重试。

    Args:
        exp (str): 要解析的课程表达式字符串。
        e_id (str): 当前选课轮次的ID。
        original_exp_for_thread (str): 用于日志记录的原始表达式字符串，以区分线程。
        courses_status_data (dict | None): 当前选课轮次所有课程的状态数据，用于特定重试逻辑。

    Returns:
        list: 选课结果列表，格式同 `elect_course` 函数的返回值。
              对于组合表达式，返回的是最终决定该表达式成功或失败的那个子表达式或课程的结果。
    '''
    # 处理 ';' (顺序) 操作符
    if ';' in exp:
        results = [parse_courses_exp(sub_exp, e_id, original_exp_for_thread, courses_status_data) for sub_exp in exp.split(';')]
        return results[-1] # 返回最后一个表达式的结果

    # 处理 '|' (或) 操作符
    if '|' in exp:
        last_result = []
        for sub_exp in exp.split('|'):
            expr_result, msg_result, succeeded_result, retry_result = parse_courses_exp(sub_exp, e_id, original_exp_for_thread, courses_status_data)
            last_result = [expr_result, msg_result, succeeded_result, retry_result]
            if succeeded_result:
                return last_result # 一旦成功，立即返回
        return last_result # 如果所有 '或' 条件都失败，返回最后一个尝试的结果

    # 处理 '&' (与) 操作符
    if '&' in exp:
        # overall_succeeded = True # Not directly used, result determined by last_result or early exit
        last_result = [] # Stores the result of the latest sub-expression
        sub_expressions = exp.split('&')
        for sub_exp in sub_expressions:
            expr_result, msg_result, succeeded_result, retry_result = parse_courses_exp(sub_exp, e_id, original_exp_for_thread, courses_status_data)
            last_result = [expr_result, msg_result, succeeded_result, retry_result] # 记录当前子表达式的结果
            if not succeeded_result:
                # overall_succeeded = False # Not strictly needed due to early return
                return last_result # 一旦失败，立即返回该失败结果
        # 如果所有 '&' 条件都成功，返回最后一个（也是成功的）结果
        return last_result


    # 基本情况：单个课程ID，尝试选课并处理重试
    # 此时的 exp 应该是单个课程ID
    current_retry = True
    final_result = []
    while current_retry:
        # elect_course 返回 [course_id, message, succeeded?, retry?]
        expr_val, msg_val, succeeded_val, retry_val = elect_course(exp, e_id, courses_status_data)
        final_result = [expr_val, msg_val, succeeded_val, retry_val]
        current_retry = retry_val # 更新重试状态

        # 打印当前尝试的结果，并带上线程信息
        print(f'[Thread for: {original_exp_for_thread}] {expr_val}: {msg_val} (succeeded:{succeeded_val}, retry:{current_retry})')
        
        if current_retry: # 如果需要重试，则等待一段时间
            sleep(interval)
        else: # 如果不需要重试（无论成功或失败），则跳出循环
            break
            
    return final_result # 返回最后一次尝试的结果


def thread_elect_courses_exps(exps: list[str], e_id: str):
    '''为每个选课表达式创建一个线程来执行选课操作。

    如果 `exps` 列表为空，则会进入交互模式，提示用户输入选课表达式。

    Args:
        exps (list[str]): 包含选课表达式字符串的列表。
        e_id (str): 当前选课轮次的ID。
    '''
    head_election(e_id) # 先访问选课页面，可能为了会话保持

    courses_status_data_for_retry = None
    if ENABLE_RETRY_ON_PERCENTAGE_LIMIT:
        try:
            print(f"[Info] Fetching course status for election {e_id} for percentage-based retry logic...")
            semester_params = get_semester_info(e_id)
            courses_status_data_for_retry = get_courses_status(semester_params)
            print(f"[Info] Successfully fetched course status for election {e_id}.")
        except Exception as e:
            print(f"[Warning] Could not fetch course status for election {e_id} (used for percentage-based retry): {e}")
            print("[Warning] Percentage-based retry for full courses will effectively be disabled for this round.")

    # 如果没有预设的选课表达式，则进入交互模式
    if len(exps) == 0:
        print('请输入您想选择的课程表达式，每个表达式占一行，以空行结束输入。')
        while True:
            exp_input = input('课程表达式: ')
            if exp_input == '': # 空行表示输入结束
                break
            exps.append(exp_input)

    threads = []
    for exp_item in exps:
        # 清理表达式：移除空格，统一逻辑运算符
        cleaned_exp = exp_item.strip().replace(' ', '')
        cleaned_exp = cleaned_exp.replace('&&', '&').replace('||', '|')

        # 创建并启动线程，将原始表达式(exp_item)用于日志追踪，并传入课程状态数据
        t = threading.Thread(target=parse_courses_exp, args=(cleaned_exp, e_id, exp_item, courses_status_data_for_retry))
        threads.append(t)
        t.start()
        sleep(threads_interval) # 控制线程启动的间隔，避免瞬间过多请求

    # 等待所有选课线程执行完毕
    for t in threads:
        t.join()


if __name__ == '__main__':
    ids = IdsAuth() # 初始化认证对象

    # 尝试从 'cookies.json' 文件加载已保存的cookies
    if os.path.exists('cookies.json'):
        try:
            with open('cookies.json', 'r') as f:
                cookies = json.load(f)
            ids = IdsAuth(cookies) # 使用加载的cookies初始化认证对象
            print('Cookies loaded successfully.')
        except Exception as e:
            print(f"Failed to load cookies: {e}. Will try to login with username/password.")
            ids = IdsAuth() # 重置为未使用cookie的状态

    # 如果没有有效的cookies或加载失败，则尝试使用用户名和密码登录
    if not ids.ok:
        print('Logging in by username and password...')
        ids.login(username, password, service)
    
    # 检查登录状态
    if ids.ok:
        # 登录成功，保存最新的cookies到 'cookies.json'
        try:
            with open('cookies.json', 'w') as f:
                json.dump(ids.cookies, f)
            print('Login success. Cookies saved.')
        except Exception as e:
            print(f"Login success, but failed to save cookies: {e}")
    else:
        print('Login failed.')
        exit(1) # 登录失败，退出程序

    # 如果在 envconfig.py 中配置了默认选课表达式，则执行它们
    if len(default_courses_exps) > 0:
        print('Processing default course expressions from envconfig.py...')
        for election_id_key, courses_exps_list in default_courses_exps.items():
            print(f"--- Starting election for profile ID: {election_id_key} ---")
            thread_elect_courses_exps(courses_exps_list, election_id_key)
            print(f"--- Finished election for profile ID: {election_id_key} ---")
        print('All default course expressions processed.')
        exit(0) # 处理完默认表达式后退出

    # --- 以下是交互模式 ---
    print('Entering interactive mode...')
    # 获取可用的选课轮次
    elections = get_elections()
    print('Available elections: ')
    for name, election_id_val in elections.items():
        print(f'  {name}: {election_id_val}')

    if len(elections) == 0:
        print('No available elections.')
        exit(0)
    elif len(elections) == 1:
        # 如果只有一个可选的选课轮次，则自动选择它
        selected_election_id = list(elections.values())[0]
        print(f'Automatically selected election: {selected_election_id}')
    else:
        # 如果有多个，提示用户选择
        selected_election_id = input('Please select an election id: ')
    print(f'Selected election ID: {selected_election_id}.')

    head_election(selected_election_id) # "预热"选定的选课轮次

    # 如果配置了跳过课程列表显示，则直接进入选课表达式输入
    if skip_course_list:
        thread_elect_courses_exps([], selected_election_id) # 传入空列表以触发交互式表达式输入
        exit(0)

    # 获取并显示课程列表
    print(f'Fetching courses for election ID: {selected_election_id}...')
    data = get_courses(selected_election_id)

    # 如果配置了检查课程余量
    if check_course_availability:
        print('Checking course availability...')
        try:
            semester_params = get_semester_info(selected_election_id)
            courses_status = get_courses_status(semester_params)
            for course in data:
                course_status = courses_status.get(str(course.get('id')))
                if course_status:
                    course['available'] = course_status.get('sc', 0) < course_status.get('lc', 0)
                else:
                    course['available'] = 'Unknown' # 如果没有状态信息，标记为未知
            # 按是否有余量和课程ID排序
            data.sort(key=lambda x: (x['available'] is not True, x.get('id')))
        except Exception as e:
            print(f"Could not check course availability: {e}")
            # 按课程ID排序
            data.sort(key=lambda x: x.get('id'))
    else:
        # 不检查余量，直接按课程ID排序
        data.sort(key=lambda x: x.get('id'))

    # 如果配置了导出课程列表到文件
    if sheet_format in ['tsv', 'xlsx']:
        try:
            df = pd.DataFrame(data)
            if sheet_format == 'tsv':
                file_name = f'{selected_election_id}.tsv'
                df.to_csv(file_name, sep='\t', index=False)
                print(f'Course list exported to {file_name}')
            elif sheet_format == 'xlsx':
                file_name = f'{selected_election_id}.xlsx'
                df.to_excel(file_name, index=False)
                print(f'Course list exported to {file_name}')
        except Exception as e:
            print(f"Failed to export course list: {e}")
    
    print(f'Please checkout full information on website' +
          (' or in the exported file.' if sheet_format in ['tsv', 'xlsx'] else '.'))

    # 打印课程列表到控制台
    print('Courses: ')
    column_keys = ['id', 'no', 'name', 'teachers']
    if check_course_availability:
        column_keys.append('available')

    # 打印表头
    header_string = '  ' + '\t'.join([str(key_name).ljust(10) for key_name in column_keys])
    print(header_string)
    # 打印每行课程信息
    for course in data:
        row_values = []
        for key in column_keys:
            value = course.get(key, 'N/A') # 如果键不存在，使用 'N/A'
            # 为了对齐，将老师信息截断或填充
            if key == 'teachers' and isinstance(value, str):
                 value = value[:18].ljust(20) # 假设老师名字段最长显示18，总共占20位
            elif key == 'name' and isinstance(value, str):
                value = value[:28].ljust(30) # 假设课程名最长显示28，总共占30位
            else:
                value = str(value).ljust(10) # 其他字段长度10
            row_values.append(value)
        print('  ' + '\t'.join(row_values))

    # 进入交互式选课表达式输入环节
    thread_elect_courses_exps([], selected_election_id) # 传入空列表以触发交互式表达式输入

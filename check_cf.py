import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import concurrent.futures
import csv
import os
import zipfile
import io

# 禁用 requests 忽略 SSL 验证时产生的安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置文件路径及参数
输入文件 = 'domains.txt'
输出文件 = 'result.csv'
进度文件 = 'progress.txt'
每次检测数量 = 2000
# 第一次运行时自动下载的域名数量（提取前10万个）
初始下载数量 = 100000
# GitHub Actions 网络极佳，可将并发数调高以显著加快检测速度
最大并发数 = 30 

# ================= 配置全局请求会话 (Session) =================
# 使用 Session 可以复用底层的 TCP 连接，避免每次请求都重新握手，大幅提高批量检测速度
会话 = requests.Session()

# 配置自动重试策略：遇到 5xx 错误时，自动重试 2 次
重试策略 = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
# 配置连接池大小与并发数相匹配
适配器 = HTTPAdapter(pool_connections=最大并发数, pool_maxsize=最大并发数, max_retries=重试策略)
会话.mount("http://", 适配器)
会话.mount("https://", 适配器)

# 全局请求头设置
全局请求头 = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
会话.headers.update(全局请求头)
# ==============================================================

def 下载并生成域名列表():
    """
    如果不存在 domains.txt，则从 Tranco 自动下载最新的全球 Top 1M 列表并提取前 10万个
    """
    if os.path.exists(输入文件):
        return

    print(f"未找到 {输入文件}，正在自动下载全球顶级域名列表 (Tranco Top 1M)...")
    try:
        url = "https://tranco-list.eu/top-1m.csv.zip"
        # 下载不使用复用的会话，单次大文件流式下载
        请求头 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        响应 = requests.get(url, headers=请求头, stream=True, timeout=30)
        响应.raise_for_status()

        print("下载完成，正在解压并寻找 CSV 文件...")
        
        # 在内存中解压并读取
        with zipfile.ZipFile(io.BytesIO(响应.content)) as 压缩包:
            # 严格匹配 .csv 结尾的文件，防止压缩包结构变化导致报错
            csv_文件名 = next((名字 for 名字 in 压缩包.namelist() if 名字.endswith('.csv')), None)
            
            if not csv_文件名:
                raise ValueError("未在压缩包中找到 .csv 结尾的数据文件。")
                
            with 压缩包.open(csv_文件名) as 文件:
                所有行 = 文件.read().decode('utf-8').splitlines()

        # 提取域名 (Tranco 格式为: 排名,域名)
        提取的域名 = []
        for 行 in 所有行[:初始下载数量]:
            if ',' in 行:
                域名 = 行.split(',')[1].strip()
                提取的域名.append(域名)

        # 写入 domains.txt
        with open(输入文件, 'w', encoding='utf-8') as 文件:
            for 域名 in 提取的域名:
                文件.write(域名 + '\n')
                
        print(f"成功获取并保存了 {len(提取的域名)} 个域名至 {输入文件}！")
        
    except Exception as 错误:
        print(f"自动下载域名列表失败: {错误}")
        # 如果下载失败，异常退出，阻止后续流程
        exit(1)

def 检测_cloudflare(域名):
    """
    检测单个域名是否使用了 Cloudflare CDN，带有 HTTPS->HTTP 降级与自动重试机制
    """
    if not 域名:
        return None

    # 清洗域名，去掉可能误加的协议头
    域名 = 域名.replace('http://', '').replace('https://', '')
    
    https_链接 = f"https://{域名}"
    http_链接 = f"http://{域名}"
    
    响应 = None
    采用协议 = "HTTPS"

    try:
        # 【核心修复】：增加 stream=True 防大文件下载假死，timeout 拆分为(连接5秒, 响应10秒)
        响应 = 会话.get(https_链接, timeout=(5, 10), allow_redirects=True, verify=False, stream=True)
    except requests.exceptions.RequestException:
        # 如果 HTTPS 失败（比如未开启 443 端口），尝试降级为 HTTP
        try:
            响应 = 会话.get(http_链接, timeout=(5, 10), allow_redirects=True, verify=False, stream=True)
            采用协议 = "HTTP"
        except requests.exceptions.RequestException:
            # 双重失败则判定为无法连接
            pass

    if 响应 is None:
        print(f"检测失败: {域名} -> 无法连接或请求超时")
        return [域名, "未知", "无", "请求超时或连接重置"]

    # 提取头信息，全部转为小写比对
    响应头 = 响应.headers
    响应头小写 = {k.lower(): v for k, v in 响应头.items()}

    # 【核心修复】：显式关闭请求流，避免连接池耗尽导致高并发线程死锁
    响应.close()

    使用了_cf = "否"
    if 'server' in 响应头小写 and 'cloudflare' in 响应头小写['server'].lower():
        使用了_cf = "是"
    elif 'cf-ray' in 响应头小写:
        使用了_cf = "是"

    print(f"检测完成: {域名} [{采用协议}] -> 状态码: {响应.status_code}, Cloudflare: {使用了_cf}")
    return [域名, 使用了_cf, 响应.status_code, "正常"]

def 获取当前进度():
    """
    从进度文件中读取上次检测到的行数
    """
    if os.path.exists(进度文件):
        with open(进度文件, 'r', encoding='utf-8') as 文件:
            try:
                内容 = 文件.read().strip()
                if 内容:
                    return int(内容)
            except ValueError:
                return 0
    return 0

def 保存当前进度(新进度):
    """
    将新的进度行数写入进度文件
    """
    with open(进度文件, 'w', encoding='utf-8') as 文件:
        文件.write(str(新进度))

def 主程序():
    # 第一步：检查并自动下载域名源数据
    下载并生成域名列表()

    # 读取全部域名列表
    with open(输入文件, 'r', encoding='utf-8') as 文件:
        所有行 = 文件.readlines()
        域名列表 = [行.strip() for 行 in 所有行 if 行.strip()]

    总数量 = len(域名列表)
    当前起始位置 = 获取当前进度()

    if 当前起始位置 >= 总数量:
        print(f"进度显示已检测 {当前起始位置} 个。所有域名已经全部检测完毕，无需再次运行。")
        return

    # 计算本次要检测的范围
    当前结束位置 = min(当前起始位置 + 每次检测数量, 总数量)
    待检测列表 = 域名列表[当前起始位置:当前结束位置]

    print(f"====== 开始执行 Cloudflare 检测 ======")
    print(f"总计资源库: {总数量} 个网址")
    print(f"本次检测区间: 第 {当前起始位置 + 1} 个 ~ 第 {当前结束位置} 个")
    print(f"实际并发任务: {len(待检测列表)} 个")
    print(f"======================================")

    结果列表 = []
    
    # 启动高并发检测
    with concurrent.futures.ThreadPoolExecutor(max_workers=最大并发数) as 执行器:
        for 结果 in 执行器.map(检测_cloudflare, 待检测列表):
            # 只有当检测结果明确为“是”时，才将其加入保存队列
            if 结果 and 结果[1] == "是":
                结果列表.append(结果)

    # 写入结果：如果是第一次运行则覆盖写入并添加表头；否则追加写入
    写入模式 = 'w' if 当前起始位置 == 0 else 'a'
    with open(输出文件, 写入模式, newline='', encoding='utf-8-sig') as 结果文件:
        写入器 = csv.writer(结果文件)
        
        # 只有在覆盖模式下才写表头
        if 写入模式 == 'w':
            写入器.writerow(['域名', '是否使用Cloudflare', 'HTTP状态码', '备注信息'])
        
        # 如果本次检测中有命中 Cloudflare 的网站，执行写入
        if 结果列表:
            写入器.writerows(结果列表)
        
    # 保存最新进度并关闭相关连接
    保存当前进度(当前结束位置)
    会话.close()
    
    print(f"====== 本次检测任务结束 ======")
    print(f"发现接入 Cloudflare 的目标: {len(结果列表)} 个")
    print(f"数据已追加至: {输出文件}")
    print(f"当前进度已更新为: {当前结束位置}")

if __name__ == "__main__":
    主程序()

import requests
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

# 全局请求头设置
全局请求头 = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def 下载并生成域名列表():
    """
    如果不存在 domains.txt，则从 Tranco 自动下载最新的全球 Top 1M 列表并提取前 10万个
    """
    if os.path.exists(输入文件):
        return

    print(f"未找到 {输入文件}，正在自动下载全球顶级域名列表 (Tranco Top 1M)...")
    try:
        url = "https://tranco-list.eu/top-1m.csv.zip"
        请求头 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        # 下载列表文件不受 500ms 限制，保持 30 秒超时以确保下载完整
        响应 = requests.get(url, headers=请求头, stream=True, timeout=30)
        响应.raise_for_status()

        print("下载完成，正在解压并寻找 CSV 文件...")
        
        with zipfile.ZipFile(io.BytesIO(响应.content)) as 压缩包:
            csv_文件名 = next((名字 for 名字 in 压缩包.namelist() if 名字.endswith('.csv')), None)
            
            if not csv_文件名:
                raise ValueError("未在压缩包中找到 .csv 结尾的数据文件。")
                
            with 压缩包.open(csv_文件名) as 文件:
                所有行 = 文件.read().decode('utf-8').splitlines()

        提取的域名 = []
        for 行 in 所有行[:初始下载数量]:
            if ',' in 行:
                域名 = 行.split(',')[1].strip()
                提取的域名.append(域名)

        with open(输入文件, 'w', encoding='utf-8') as 文件:
            for 域名 in 提取的域名:
                文件.write(域名 + '\n')
                
        print(f"成功获取并保存了 {len(提取的域名)} 个域名至 {输入文件}！")
        
    except Exception as 错误:
        print(f"自动下载域名列表失败: {错误}")
        exit(1)

def 发送极速安全请求(url):
    """
    极速侦测模式：最大等待时间 500ms (0.5秒)。
    超时即抛弃，不做任何过多停留，确保大部队进度。
    """
    for 尝试次数 in range(2): # 总共尝试 2 次 (失败重试 1 次)
        try:
            # 【核心修改】：将 timeout 设置为 0.5，严格控制单次网络通讯上限为 500ms
            响应 = requests.get(url, headers=全局请求头, timeout=0.5, allow_redirects=True, verify=False, stream=True)
            return 响应
        except requests.exceptions.RequestException:
            pass # 发生超时(超过500ms)或连接错误则直接进入下一次尝试或放弃
    return None

def 检测_cloudflare(域名):
    """
    检测单个域名是否使用了 Cloudflare CDN
    """
    if not 域名:
        return None

    域名 = 域名.replace('http://', '').replace('https://', '')
    
    https_链接 = f"https://{域名}"
    http_链接 = f"http://{域名}"
    
    采用协议 = "HTTPS"
    响应 = 发送极速安全请求(https_链接)
    
    if 响应 is None:
        # 如果 HTTPS 极速探测失败，降级尝试 HTTP
        响应 = 发送极速安全请求(http_链接)
        采用协议 = "HTTP"

    if 响应 is None:
        print(f"自动跳过: {域名} -> 响应超过 500ms 或无法连接")
        return [域名, "未知", "无", "请求超时"]

    响应头小写 = {k.lower(): v for k, v in 响应.headers.items()}
    响应.close()

    使用了_cf = "否"
    if 'server' in 响应头小写 and 'cloudflare' in 响应头小写['server'].lower():
        使用了_cf = "是"
    elif 'cf-ray' in 响应头小写:
        使用了_cf = "是"

    print(f"检测完成: {域名} [{采用协议}] -> 状态码: {响应.status_code}, Cloudflare: {使用了_cf}")
    return [域名, 使用了_cf, 响应.status_code, "正常"]

def 获取当前进度():
    """从进度文件中读取上次检测到的行数"""
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
    """将新的进度行数写入进度文件"""
    with open(进度文件, 'w', encoding='utf-8') as 文件:
        文件.write(str(新进度))

def 主程序():
    下载并生成域名列表()

    with open(输入文件, 'r', encoding='utf-8') as 文件:
        所有行 = 文件.readlines()
        域名列表 = [行.strip() for 行 in 所有行 if 行.strip()]

    总数量 = len(域名列表)
    当前起始位置 = 获取当前进度()

    if 当前起始位置 >= 总数量:
        print(f"进度显示已检测 {当前起始位置} 个。所有域名已经全部检测完毕，无需再次运行。")
        return

    当前结束位置 = min(当前起始位置 + 每次检测数量, 总数量)
    待检测列表 = 域名列表[当前起始位置:当前结束位置]

    print(f"====== 开始执行极速 Cloudflare 检测 ======")
    print(f"总计资源库: {总数量} 个网址")
    print(f"本次检测区间: 第 {当前起始位置 + 1} 个 ~ 第 {当前结束位置} 个")
    print(f"实际并发任务: {len(待检测列表)} 个")
    print(f"单网址检测超时: 500ms")
    print(f"==========================================")

    结果列表 = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=最大并发数) as 执行器:
        任务集合 = [执行器.submit(检测_cloudflare, 域名) for 域名 in 待检测列表]
        
        for 任务 in concurrent.futures.as_completed(任务集合):
            结果 = 任务.result()
            if 结果 and 结果[1] == "是":
                结果列表.append(结果)

    # 写入结果
    写入模式 = 'w' if 当前起始位置 == 0 else 'a'
    with open(输出文件, 写入模式, newline='', encoding='utf-8-sig') as 结果文件:
        写入器 = csv.writer(结果文件)
        if 写入模式 == 'w':
            写入器.writerow(['域名', '是否使用Cloudflare', 'HTTP状态码', '备注信息'])
        if 结果列表:
            写入器.writerows(结果列表)
        
    保存当前进度(当前结束位置)
    
    print(f"====== 本次检测任务结束 ======")
    print(f"发现接入 Cloudflare 的目标: {len(结果列表)} 个")
    print(f"数据已追加至: {输出文件}")
    print(f"当前进度已更新为: {当前结束位置}")

if __name__ == "__main__":
    主程序()

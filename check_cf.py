import requests
import urllib3
import concurrent.futures
import csv
import os
import zipfile
import io
import time  

# 禁用 requests 忽略 SSL 验证时产生的安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置文件路径及参数
输入文件 = 'domains.txt'
输出文件 = 'result.csv'
进度文件 = 'progress.txt'

每次检测数量 = 20000  
分块大小 = 1000 
最大安全运行时间 = 510 

初始下载数量 = 100000
最大并发数 = 30 

# 全局请求头设置
全局请求头 = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def 下载并生成域名列表():
    if os.path.exists(输入文件):
        return
    print(f"未找到 {输入文件}，正在自动下载全球顶级域名列表 (Tranco Top 1M)...")
    try:
        url = "https://tranco-list.eu/top-1m.csv.zip"
        请求头 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
    """极速侦测：最大等待时间 500ms。捕获一切底层解析错误。"""
    for 尝试次数 in range(2): 
        try:
            响应 = requests.get(url, headers=全局请求头, timeout=0.5, allow_redirects=True, verify=False, stream=True)
            return 响应
        except Exception: 
            # 【修复点2：战术级拦截】将 RequestException 扩大为通用的 Exception。
            # 无论是 LocationParseError 还是 InvalidSchema，统统按失败处理，不抛出异常。
            pass 
    return None

def 检测_cloudflare(域名):
    if not 域名:
        return None

    # 【修复点1：输入端清洗】深度清理域名，去除前导点号(.)、斜杠(/)和星号(*)
    域名 = 域名.replace('http://', '').replace('https://', '').strip(' ./*')
    if not 域名:
        return None
    
    https_链接 = f"https://{域名}"
    http_链接 = f"http://{域名}"
    
    采用协议 = "HTTPS"
    响应 = 发送极速安全请求(https_链接)
    
    if 响应 is None:
        响应 = 发送极速安全请求(http_链接)
        采用协议 = "HTTP"

    if 响应 is None:
        print(f"自动跳过: {域名} -> 响应超时或由于畸形网址无法连接")
        return [域名, "未知", "无", "无法连接"]

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
    with open(进度文件, 'w', encoding='utf-8') as 文件:
        文件.write(str(新进度))

def 结果文件去重(目标文件):
    if not os.path.exists(目标文件):
        return
    print(f"正在对 {目标文件} 执行全局去重和清理操作...")
    已存在域名 = set()
    去重后的行 = []
    表头 = None
    try:
        with open(目标文件, 'r', encoding='utf-8-sig') as 文件:
            读取器 = csv.reader(文件)
            try:
                表头 = next(读取器)
            except StopIteration:
                return
            for 行 in 读取器:
                if not 行: continue
                域名 = 行[0]
                if 域名 not in 已存在域名:
                    已存在域名.add(域名)
                    去重后的行.append(行)

        with open(目标文件, 'w', newline='', encoding='utf-8-sig') as 文件:
            写入器 = csv.writer(文件)
            写入器.writerow(表头)
            写入器.writerows(去重后的行)
        print(f"去重完成！去除冗余后，当前共保留 {len(去重后的行)} 条有效记录。")
    except Exception as e:
        print(f"去重操作发生异常: {e}")

def 主程序():
    程序启动时间 = time.time()  
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

    print(f"====== 开始执行专业级 Cloudflare 扫描 ======")
    print(f"总计资源库: {总数量} 个网址")
    print(f"本次分配区间: 第 {当前起始位置 + 1} 个 ~ 第 {当前结束位置} 个")
    print(f"实际待测任务: {len(待检测列表)} 个")
    print(f"安全机制: 500ms硬超时 + {分块大小}个/区块断点存档 + {最大安全运行时间}秒软超时结束")
    print(f"=============================================")

    写入模式 = 'w' if 当前起始位置 == 0 and not os.path.exists(输出文件) else 'a'
    已处理总数 = 0
    本次新增有效记录数 = 0

    for i in range(0, len(待检测列表), 分块大小):
        当前区块列表 = 待检测列表[i:i + 分块大小]
        区块结果 = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=最大并发数) as 执行器:
            任务集合 = [执行器.submit(检测_cloudflare, 域名) for 域名 in 当前区块列表]
            for 任务 in concurrent.futures.as_completed(任务集合):
                # 【修复点3：战略级隔离】为任务结果读取增加异常护盾
                try:
                    结果 = 任务.result()
                    if 结果 and 结果[1] == "是":
                        区块结果.append(结果)
                except Exception as 错误:
                    print(f"警告：单个检测任务发生致命崩溃已隔离处理")

        with open(输出文件, 写入模式, newline='', encoding='utf-8-sig') as 结果文件:
            写入器 = csv.writer(结果文件)
            if 写入模式 == 'w':
                写入器.writerow(['域名', '是否使用Cloudflare', 'HTTP状态码', '备注信息'])
                写入模式 = 'a'  
            if 区块结果:
                写入器.writerows(区块结果)
                本次新增有效记录数 += len(区块结果)

        已处理总数 += len(当前区块列表)
        当前安全进度 = 当前起始位置 + 已处理总数
        保存当前进度(当前安全进度)
        print(f"\n[存档点] 已安全保存阶段进度: {当前安全进度} / {总数量}\n")

        已耗时 = time.time() - 程序启动时间
        if 已耗时 >= 最大安全运行时间:
            print(f"⚠️ [防溢出机制] 脚本运行已达 {已耗时:.1f} 秒，接近系统时间极限！")
            print("⚠️ 触发优雅软超时，已主动切断后续任务队列，准备安全移交 Git 推送...")
            break

    结果文件去重(输出文件)
    
    最终进度 = 获取当前进度()
    print(f"====== 本次检测任务完美收官 ======")
    print(f"总耗时: {time.time() - 程序启动时间:.1f} 秒")
    print(f"本次运行新增记录: {本次新增有效记录数} 个")
    print(f"当前整体进度已更新至: {最终进度}")

if __name__ == "__main__":
    主程序()

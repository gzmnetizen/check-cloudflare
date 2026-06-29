import csv
import random
import socket
import time

# 常见域名黑名单（可根据你的标准自行增删）
COMMON_DOMAINS = # 常见域名黑名单（扩展至前100个常见域名，可根据你的标准自行增删）
COMMON_DOMAINS = {
    'google.com', 'youtube.com', 'facebook.com', 'baidu.com', 'wikipedia.org',
    'qq.com', 'taobao.com', 'yahoo.com', 'tmall.com', 'amazon.com',
    'twitter.com', 'sohu.com', 'jd.com', 'live.com', 'instagram.com',
    'sina.com.cn', 'weibo.com', 'yandex.ru', '360.cn', 'vk.com',
    'reddit.com', 'netflix.com', 'linkedin.com', 'twitch.tv', 'microsoft.com',
    'bing.com', 'office.com', 'ebay.com', 'alipay.com', 'csdn.net',
    'yahoo.co.jp', 'mail.ru', 'ok.ru', 'whatsapp.com', 'bilibili.com',
    'spotify.com', 'apple.com', 'tiktok.com', 'github.com', 'naver.com',
    'discord.com', 'zhihu.com', 'samsung.com', 'pinterest.com', 'weather.com',
    'quora.com', 'microsoftonline.com', 'x.com', 'chatgpt.com', 'openai.com',
    'zoom.us', 'shopify.com', 'duckduckgo.com', 'fandom.com', 'msn.com',
    'vimeo.com', 'tumblr.com', 'medium.com', 'bbc.com', 'cnn.com',
    'nytimes.com', 'wordpress.com', 'blogspot.com', 'paypal.com', 'adobe.com',
    'canva.com', 'aliexpress.com', 'dropbox.com', 'stackoverflow.com', 'imdb.com',
    'hulu.com', 'cnbc.com', 'forbes.com', 'espn.com', 'booking.com',
    'tripadvisor.com', 'craigslist.org', 'zillow.com', 'etsy.com', 'walmart.com',
    'ikea.com', 'homedepot.com', 'target.com', 'reuters.com', 'bloomberg.com',
    'wsj.com', 'theguardian.com', 'dailymail.co.uk', 'foxnews.com', 'usatoday.com',
    'nypost.com', 'salesforce.com', 'cloudflare.com', 'cisco.com', 'intel.com',
    'oracle.com', 'ibm.com', 'aws.amazon.com', 'azure.com', 'github.io'
}

def is_uncommon(domain):
    """
    判断是否为不常见域名
    这里采用的简单逻辑是：如果域名包含在常见列表内，或属于常见主域名，则剔除。
    """
    for common in COMMON_DOMAINS:
        if domain == common or domain.endswith('.' + common):
            return False
    return True

def get_ip(domain):
    """解析域名获取IP"""
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None

def test_tcp_latency(ip, port=443, timeout=2.0):
    """测试指定 IP 和端口的 TCP 延迟 (毫秒)"""
    start_time = time.time()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            latency = (time.time() - start_time) * 1000
            return latency
    except (socket.timeout, ConnectionRefusedError, OSError):
        return None

def main():
    domains = []
    
    # 严谨读取本地的 result.csv
    try:
        with open('result.csv', mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # 跳过表头
            for row in reader:
                if row and len(row) >= 1:
                    domains.append(row[0].strip())
    except FileNotFoundError:
        print("未找到 result.csv，请先确保数据源存在。")
        return

    # 随机选取 100 个域名 (如果总数不足100则全选)
    sample_size = min(100, len(domains))
    selected_domains = random.sample(domains, sample_size)
    
    # 筛选出不常见域名
    uncommon_domains = [d for d in selected_domains if is_uncommon(d)]
    
    results = []
    for domain in uncommon_domains:
        ip = get_ip(domain)
        if ip:
            latency = test_tcp_latency(ip)
            if latency is not None:
                results.append((ip, latency, domain))
    
    # 按照延迟从小到大排序
    results.sort(key=lambda x: x[1])
    
    # 仅保留延时最快的前5个
    top_5_results = results[:5]
    
    # 结果写入 ip.txt，仅保存域名
    with open('ip.txt', mode='w', encoding='utf-8') as f:
        for ip, latency, domain in top_5_results:
            f.write(f"{domain}\n")

if __name__ == '__main__':
    main()

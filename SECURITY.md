# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Chúng tôi lấy security seriously. Nếu bạn phát hiện lỗ hổng bảo mật, vui lòng:

1. **KHÔNG** tạo public GitHub issue — báo cáo riêng tư qua [Security Advisories](https://github.com/nguyenson/app-free-api-information-retrieval/security/advisories/new).
2. Mô tả chi tiết lỗ hổng (loại, payload, tác động).
3. Chúng tôi sẽ phản hồi trong vòng 48 giờ và cố fix trong 2 tuần.
4. Nếu lỗi được xác nhận, chúng tôi sẽ công bố trong CHANGELOG sau khi đã patch.

## Best Practices khi dùng tool

- **KHÔNG commit file `.env`** — nó chứa API key thật. File này đã được `.gitignore`.
- **Luôn verify API key** trước khi dùng — kiểm tra bằng `python run.py check --provider <name>`.
- **Rate limit** — tool tuân thủ rate limit của mỗi provider. Không spam endpoint.
- **Privacy** — `discover-live` gọi OpenRouter `/models` (public, không cần key).
  Không gửi dữ liệu nhạy cảm đến bên thứ ba không đáng tin cậy.

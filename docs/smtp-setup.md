
## 이메일 인증 SMTP 설정

회원가입 이메일 인증을 실제 Gmail SMTP로 발송하려면 `.env.example`의 이메일 설정을 `.env`에 채웁니다.

- `EMAIL_HOST_USER`: 발송에 사용할 Gmail 주소
- `EMAIL_HOST_PASSWORD`: Gmail 계정 비밀번호가 아니라 Google 앱 비밀번호
- `DEFAULT_FROM_EMAIL`: 메일에 표시할 발신자 주소

Google 앱 비밀번호는 Google 계정 2단계 인증을 켠 뒤 발급받아야 합니다.
`.env`에는 민감정보가 들어가므로 저장소에 커밋하지 않습니다.

회원가입 비밀번호는 Django `BCryptSHA256PasswordHasher`로 저장합니다.
salt는 Django password hasher가 비밀번호 저장 시 자동 생성합니다.
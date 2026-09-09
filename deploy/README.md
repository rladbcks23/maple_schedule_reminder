# 오라클 클라우드 무료 VM 배포

봇은 웹서버가 아니라 **디스코드 쪽으로 먼저 접속해 연결을 붙들고 있는** 프로그램입니다.
그래서 도메인도, 인바운드 포트 개방도, HTTPS도 필요 없습니다. 나가는 인터넷만 되면 됩니다.
배포란 결국 *꺼지지 않는 컴퓨터에서 `python -m bot.main` 을 계속 돌리는 것* 입니다.

## 1. VM 만들기

[cloud.oracle.com](https://cloud.oracle.com) 에서 계정을 만듭니다. 카드 등록을 요구하지만
**Always Free 리소스만 쓰면 청구되지 않습니다.** 가입 후 유료 전환을 하지 않으면 한도를
넘는 순간 생성이 막힐 뿐 과금은 안 됩니다.

Compute → Instances → **Create Instance**

| 항목 | 고를 것 |
| --- | --- |
| Image | **Ubuntu 24.04** (파이썬 3.12가 기본이라 따로 설치할 게 없습니다) |
| Shape | `VM.Standard.E2.1.Micro` (AMD, Always Free) |
| SSH keys | 공개키 붙여넣기 또는 키 쌍 다운로드 |

`VM.Standard.A1.Flex` (ARM) 가 사양은 훨씬 좋지만 **Out of capacity 로 자주 거절됩니다.**
이 봇은 메모리를 거의 안 써서 AMD Micro(1 OCPU / 1GB)로 충분합니다.

인바운드 규칙은 손대지 않아도 됩니다. SSH(22)만 열려 있으면 되고, 그건 기본입니다.

## 2. 접속하고 코드 받기

```bash
ssh -i ~/받은키.key ubuntu@<VM_공인IP>
```

```bash
sudo apt update
sudo apt install -y python3-venv git
git clone https://github.com/rladbcks23/maple_schedule_reminder.git
cd maple_schedule_reminder
python3 -m venv .venv
.venv/bin/pip install -e .
```

## 3. 토큰 넣기

```bash
cp .env.example .env
nano .env          # DISCORD_TOKEN 줄에 봇 토큰 붙여넣기
chmod 600 .env     # 다른 계정이 못 읽게
```

`GUILD_ID` 는 비워두면 전역 등록(반영에 최대 1시간), 서버 ID를 넣으면 즉시 반영됩니다.

## 4. DB 만들기

```bash
.venv/bin/python -m alembic upgrade head
```

`maple_boss_bot.db` 파일이 생깁니다. **등록한 캐릭터·파티·알림 채널이 전부 이 파일에 들어갑니다.**
VM 디스크에 그대로 남으므로 재시작해도 사라지지 않습니다. 다만 VM 자체를 지우면 같이 사라지니,
사람이 많이 쓰기 시작하면 가끔 백업해두세요.

```bash
cp maple_boss_bot.db ~/backup-$(date +%F).db
```

## 5. 서비스로 등록

한 번 등록해두면 봇이 죽어도 자동으로 다시 뜨고, VM을 재부팅해도 알아서 시작합니다.

```bash
sudo cp deploy/maple-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now maple-bot
```

확인:

```bash
sudo systemctl status maple-bot        # active (running) 이면 성공
journalctl -u maple-bot -f             # 실시간 로그 (Ctrl+C 로 빠져나옴)
```

로그에 `로그인 완료: ...` 와 `슬래시 커맨드 15개 동기화` 가 뜨면 됩니다.

## 6. 업데이트

코드를 고쳐 GitHub에 push한 뒤, 서버에서:

```bash
~/maple_schedule_reminder/deploy/update.sh
```

`git pull` → 의존성 → 마이그레이션 → 재시작을 한 번에 합니다. 처음 한 번만 실행 권한을 줍니다.

```bash
chmod +x deploy/update.sh
```

## 자주 겪는 것

**봇은 떴는데 알림이 안 와요** — 서버에서 `/알림채널` 을 지정하지 않으면 알림이 나가지 않습니다.
에러 없이 조용히 건너뛰므로 눈치채기 어렵습니다. `/알림설정확인` 으로 확인하세요.

**커맨드가 안 보여요** — `GUILD_ID` 를 비워두면 전역 등록이라 최대 1시간 걸립니다.
바로 쓰고 싶으면 `.env` 에 서버 ID를 넣고 `sudo systemctl restart maple-bot`.

**`status` 가 failed 예요** — `journalctl -u maple-bot -n 50` 으로 이유를 봅니다.
대개 토큰이 비었거나(`DISCORD_TOKEN이 비어 있습니다`), 마이그레이션을 안 돌린 경우입니다.

**로그에 PyNaCl 경고가 떠요** — 음성 기능용 라이브러리라 이 봇에는 필요 없습니다. 무시하세요.
`Privileged message content intent is missing` 도 마찬가지입니다. 슬래시 커맨드만 쓰니까요.

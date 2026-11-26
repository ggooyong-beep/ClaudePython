20261125_Info
25일 AI 테스팅 교육 공유용

Jenkins 설치
OpenjDK 설치
세번째 옵션인 JAVA_HOME 환경변수를 선택하여 설치한다.
Docker Desktop 설치
다운로드: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe?utm_source=docker&utm_medium=webreferral&utm_campaign=docs-driven-download-win-amd64&_gl=1*1u5bhh7*_gcl_au*NTA5ODU2NTk0LjE3OTU2Njk0NDE.*_ga*MjQxNDA5NDAwLjE3OTU2Njk0NDE.*_ga_XJWPQMJYHQ*czE3OTU2Njk0NDAkbzEkZzEkdDE3OTU2Njk0NDEkajU5JGwwJGgw
Claude Skill
System-Test-Skill
SW의 시스템 테스트 케이스를 생성하기 위한 스킬을 만들어줘. 다음을 반영해줘

A-SPICE 및 ISO26262 Part 6의 요건을 만족시키는 테스트 케이스 생성
테스트 케이스 양식을 적영하되, 만약 주어진 양식이 없으면 다음의 항목을 포함하여 생성
테스트 케이스 ID, 테스트 베이시스 ID, 테스트 목적, 입력값, 절차, 예상 출력값, 사용한 테스트 기법
다음 기법을 반드시 적용해줘. 경계값분석, 동치 클래스
다음 기법은 활용할 수 있다면 적용해줘: 페어와이즈
페어와이즈는 반드시 Giuhub에 있는 PICT 도구를 활용해서 테스트 케이스 도출해줘.
테스트 베이시스 대비 100% 추적성을 보장해줘.
테스트 베이시스 커버리지 100% 달성해줘.
커버리지만을 채우기 위한 쓰레기같은 테스트 케이스 생성하지 말아줘.
실행 가능한 테스트 케이스만을 생성해.
네가 추가적으로 제안하는 테스트 케이스에는 "제안" 이라고 표시해줘.
기능 테스트와 비기능 테스트를 시트로 구분해줘.
엣지에 대한 테스트 케이스 추가해줘. 그리고 케이스는 WoW 검증이라고 기법을 명시해줘.
Subagent
system-test-case 생성 서브 에이전트
이 서브 에이전트는 SW 시스템 테스트 케이스를 생성하는 서브 에이전트입니다. 이 서브 에이전트는 다음을 준수합니다.

반드시 sw-system-test-case 스킬을 사용합니다.
모델은 Sonnet 5.5를 사용합니다.
테스트의 목적은 결함 발견입니다. 결함 발견하기 위한 테스트 케이스를 생성합니다.
테스트는 주어진 양식을 활용하거나, 없는 경우 스킬에 따라 생성합니다.
스킬에 주어진 테스트 케이스 생성 조건을 만족합니다.
이 서브 에이전트는 SW 요구사항이 분석이 완료된 후, 시스템 테스트 케이스를 생성하는 단계에서 사용합니다.
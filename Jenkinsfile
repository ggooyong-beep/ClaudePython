// 품질 게이트 파이프라인: Ruff -> Pytest(Branch 커버리지 100%) -> 주석률(cloc) 20% 이상 -> 추적성
// Jenkins 에이전트에는 Python 3.12 이상과 cloc이 설치되어 있어야 한다.
def run(String cmd) {
    if (isUnix()) { sh cmd } else { bat cmd }
}

pipeline {
    agent any
    options { timestamps() }
    stages {
        stage('환경 구성') {
            steps {
                run('python -m venv .venv')
                script {
                    def pip = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run("${pip} -m pip install -e .[dev]")
                }
            }
        }
        stage('정적분석 (Ruff)') {
            steps {
                script {
                    def py = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run("${py} -m ruff check .")
                }
            }
        }
        stage('단위 테스트와 커버리지 (Pytest)') {
            steps {
                script {
                    def py = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run("${py} -m pytest --cov-report=xml")
                }
            }
        }
        stage('주석률 게이트 (cloc)') {
            steps {
                script {
                    def py = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run('cloc --json --by-file --out=cloc.json src tools')
                    run("${py} tools/quality_gate.py cloc.json --min 20 --prefix src/ --prefix tools/")
                }
            }
        }
        stage('추적성 게이트') {
            steps {
                script {
                    def py = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run("${py} tools/trace_check.py docs/01_requirements/01_swr.md docs/01_requirements/oem_requirements.txt")
                    run("${py} tools/unit_trace.py docs/01_requirements/01_swr.md tests/childlock")
                }
            }
        }
    }
}

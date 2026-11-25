import type { Answer } from '../types'

export function Transcript({ answers }: { answers: Answer[] }) {
  return <>{answers.map((answer, i) => <div className="exchange" key={answer.id}>
    <div className="question-meta">主问题 {answer.question.main_index + 1}{answer.question.followup > 0 && ` · 追问 ${answer.question.followup}`}</div>
    <h3>{answer.question.text}</h3><div className="answer-bubble"><span>我的回答 {i + 1} · 已保存</span><p>{answer.text}</p></div>
  </div>)}</>
}

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import UsernameInput from '../components/UsernameInput'

describe('UsernameInput', () => {
  it('disables submit button when username is empty', () => {
    render(<UsernameInput onAnalyze={vi.fn()} isLoading={false} />)
    const button = screen.getByRole('button', { name: /analyze/i })
    expect(button).toBeDisabled()
  })

  it('enables submit button when username is entered', () => {
    render(<UsernameInput onAnalyze={vi.fn()} isLoading={false} />)
    const input = screen.getByPlaceholderText(/magnus/i)
    fireEvent.change(input, { target: { value: 'noob042' } })
    const button = screen.getByRole('button', { name: /analyze/i })
    expect(button).not.toBeDisabled()
  })

  it('calls onAnalyze with trimmed username on submit', () => {
    const onAnalyze = vi.fn()
    render(<UsernameInput onAnalyze={onAnalyze} isLoading={false} />)
    const input = screen.getByPlaceholderText(/magnus/i)
    fireEvent.change(input, { target: { value: '  noob042  ' } })
    fireEvent.submit(screen.getByRole('button', { name: /analyze/i }))
    expect(onAnalyze).toHaveBeenCalledWith('noob042', 12, 'all')
  })

  it('does not call onAnalyze when username is whitespace only', () => {
    const onAnalyze = vi.fn()
    render(<UsernameInput onAnalyze={onAnalyze} isLoading={false} />)
    const input = screen.getByPlaceholderText(/magnus/i)
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.submit(input.closest('form'))
    expect(onAnalyze).not.toHaveBeenCalled()
  })
})

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  isStreaming?: boolean;
}

interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ inline, className, children, ...props }) => {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const textContent = String(children).replace(/\n$/, '');

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
    }
  };

  if (inline) {
    return (
      <code
        style={{
          fontFamily: 'var(--font-precision)',
          fontSize: '0.9em',
          padding: '2px 5px',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--color-paper-dark)',
          border: '1px solid var(--color-rule)',
          color: 'var(--color-ink)',
          wordBreak: 'break-word',
        }}
        {...props}
      >
        {children}
      </code>
    );
  }

  return (
    <div
      style={{
        margin: '12px 0',
        borderRadius: 'var(--radius-sm)',
        border: '1.5px solid var(--color-rule)',
        background: 'var(--color-paper-dark)',
        overflow: 'hidden',
        boxShadow: '1px 1px 0 var(--color-rule)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 10px',
          background: 'var(--color-paper)',
          borderBottom: '1px solid var(--color-rule)',
          fontSize: '11px',
          fontFamily: 'var(--font-precision)',
          fontWeight: 700,
          color: 'var(--color-ink-soft)',
          userSelect: 'none',
        }}
      >
        <span>{language ? language.toUpperCase() : 'CODE'}</span>
        <button
          type="button"
          onClick={handleCopy}
          title="Copy code"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            background: 'var(--color-paper-raised)',
            border: '1px solid var(--color-rule)',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 6px',
            fontSize: '10px',
            fontFamily: 'var(--font-precision)',
            fontWeight: 700,
            color: 'var(--color-ink)',
            cursor: 'pointer',
          }}
        >
          {copied ? (
            <>
              <Check size={11} color="var(--color-ledger-green)" />
              <span>COPIED</span>
            </>
          ) : (
            <>
              <Copy size={11} />
              <span>COPY</span>
            </>
          )}
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: '12px',
          overflowX: 'auto',
          fontFamily: 'var(--font-precision)',
          fontSize: '12px',
          lineHeight: '1.5',
          color: 'var(--color-ink)',
          background: 'transparent',
        }}
      >
        <code>{children}</code>
      </pre>
    </div>
  );
};

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
  isStreaming = false,
}) => {
  return (
    <div
      className={`markdown-body ${className}`}
      style={{
        fontFamily: 'var(--font-precision)',
        fontSize: 'var(--text-body-sm)',
        lineHeight: '1.6',
        color: 'var(--color-ink)',
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1
              style={{
                fontSize: '1.25em',
                fontWeight: 800,
                marginTop: '16px',
                marginBottom: '8px',
                paddingBottom: '4px',
                borderBottom: '1.5px solid var(--color-rule)',
                color: 'var(--color-ink)',
                letterSpacing: '0.02em',
              }}
            >
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2
              style={{
                fontSize: '1.15em',
                fontWeight: 800,
                marginTop: '14px',
                marginBottom: '6px',
                color: 'var(--color-win-blue)',
                letterSpacing: '0.02em',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span
                style={{
                  width: '4px',
                  height: '14px',
                  background: 'var(--color-win-blue)',
                  borderRadius: '1px',
                  display: 'inline-block',
                }}
              />
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              style={{
                fontSize: '1.05em',
                fontWeight: 700,
                marginTop: '12px',
                marginBottom: '4px',
                color: 'var(--color-ink)',
              }}
            >
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4
              style={{
                fontSize: '0.95em',
                fontWeight: 700,
                marginTop: '10px',
                marginBottom: '4px',
                color: 'var(--color-ink-soft)',
                textTransform: 'uppercase',
                letterSpacing: '0.03em',
              }}
            >
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p
              style={{
                marginTop: '6px',
                marginBottom: '6px',
                lineHeight: '1.65',
              }}
            >
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul
              style={{
                marginTop: '6px',
                marginBottom: '8px',
                paddingLeft: '20px',
                listStyleType: 'disc',
              }}
            >
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol
              style={{
                marginTop: '6px',
                marginBottom: '8px',
                paddingLeft: '20px',
                listStyleType: 'decimal',
              }}
            >
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li
              style={{
                marginTop: '3px',
                marginBottom: '3px',
                lineHeight: '1.55',
              }}
            >
              {children}
            </li>
          ),
          table: ({ children }) => (
            <div
              style={{
                overflowX: 'auto',
                margin: '12px 0',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                boxShadow: '1.5px 1.5px 0 var(--color-rule)',
              }}
            >
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '11.5px',
                  fontFamily: 'var(--font-precision)',
                  textAlign: 'left',
                }}
              >
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead
              style={{
                background: 'var(--color-paper-dark)',
                borderBottom: '1.5px solid var(--color-rule)',
                color: 'var(--color-ink)',
                fontWeight: 800,
              }}
            >
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th
              style={{
                padding: '7px 10px',
                borderRight: '1px solid var(--color-rule)',
                letterSpacing: '0.03em',
                textTransform: 'uppercase',
                fontSize: '10.5px',
              }}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              style={{
                padding: '6px 10px',
                borderBottom: '1px solid var(--color-rule)',
                borderRight: '1px solid var(--color-rule)',
                color: 'var(--color-ink)',
              }}
            >
              {children}
            </td>
          ),
          tr: ({ children }) => (
            <tr
              style={{
                transition: 'background 0.15s ease',
              }}
            >
              {children}
            </tr>
          ),
          blockquote: ({ children }) => (
            <blockquote
              style={{
                margin: '10px 0',
                padding: '8px 14px',
                borderLeft: '4px solid var(--color-win-blue)',
                background: 'var(--color-paper-dark)',
                borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                color: 'var(--color-ink-soft)',
                fontStyle: 'normal',
              }}
            >
              {children}
            </blockquote>
          ),
          hr: () => (
            <hr
              style={{
                border: 'none',
                borderTop: '1.5px solid var(--color-rule)',
                margin: '14px 0',
              }}
            />
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--color-win-blue)',
                textDecoration: 'underline',
                fontWeight: 600,
              }}
            >
              {children}
            </a>
          ),
          strong: ({ children }) => (
            <strong style={{ fontWeight: 800, color: 'var(--color-ink)' }}>
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em style={{ fontStyle: 'italic' }}>{children}</em>
          ),
          code: CodeBlock as any,
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span
          className="typewriter-cursor"
          style={{
            display: 'inline-block',
            width: '7px',
            height: '13px',
            background: 'var(--color-win-blue)',
            marginLeft: '4px',
            verticalAlign: 'middle',
            animation: 'blink 0.8s infinite',
          }}
        />
      )}
    </div>
  );
};

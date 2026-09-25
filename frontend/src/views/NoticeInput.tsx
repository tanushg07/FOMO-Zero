import React, { useRef, useState } from 'react';
import { ErrorState } from '../components/ErrorState';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createNotice, extractNotice } from '../api';

export const NoticeInput: React.FC = () => {
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();

  const processNoticeMutation = useMutation({
    mutationFn: async () => {
      const notice = await createNotice({ text, title, file: file ?? undefined });
      return extractNotice(notice.id);
    },
    onSuccess: () => {
      setText('');
      setTitle('');
      setFile(null);
      queryClient.invalidateQueries({ queryKey: ['notices'] });
      window.location.hash = '#dashboard';
    }
  });

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      const validTypes = ['.txt', '.pdf', '.docx'];
      const isValid = validTypes.some(type => file.name.toLowerCase().endsWith(type));
      if (!isValid) {
        setFileError(`Invalid file type. Supported: ${validTypes.join(', ')}`);
      } else {
        setFileError(null);
        setFile(file);
        setText('');
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div className="flex flex-col h-[70vh] max-w-4xl mx-auto gap-4">
      <h2 className="font-sans text-xl uppercase tracking-widest border-b border-zinc-800 pb-2">Submit College Notice</h2>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Optional notice title"
        className="border border-zinc-800 bg-zinc-900 p-3 text-sm text-zinc-200 focus:border-zinc-600 focus:outline-none"
      />
      <div className="flex-grow relative flex flex-col border border-zinc-800 focus-within:border-zinc-600 transition-colors bg-zinc-900">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste notice text here..."
          className="w-full h-full bg-transparent resize-none p-4 text-zinc-200 focus:outline-none font-sans text-sm"
        />
        <div className="absolute bottom-2 right-2 text-xs font-mono text-zinc-500">
          {text.length} CHARS
        </div>
      </div>
      
      <div 
        onDrop={handleFileDrop}
        onDragOver={handleDragOver}
        className="border border-zinc-800 border-dashed p-6 text-center text-sm font-mono text-zinc-500 hover:text-zinc-300 hover:border-zinc-600 transition-colors"
      >
        <button type="button" onClick={() => fileInputRef.current?.click()} className="underline underline-offset-4">
          {file ? file.name : 'DROP FILE (.txt, .pdf, .docx) OR BROWSE'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.pdf,.docx"
          className="hidden"
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (!selected) return;
            const valid = ['.txt', '.pdf', '.docx'].some((extension) => selected.name.toLowerCase().endsWith(extension));
            if (!valid) setFileError('Invalid file type. Supported: .txt, .pdf, .docx');
            else { setFileError(null); setFile(selected); setText(''); }
          }}
        />
      </div>
      
      {fileError && <ErrorState message={fileError} />}

      <button
        disabled={(!text.trim() && !file) || processNoticeMutation.isPending}
        className="w-full bg-zinc-100 text-black py-4 uppercase font-bold tracking-widest disabled:opacity-50 disabled:bg-zinc-800 disabled:text-zinc-500 transition-colors border border-transparent"
        onClick={() => processNoticeMutation.mutate()}
      >
        {processNoticeMutation.isPending ? 'PROCESSING...' : 'SUBMIT NOTICE'}
      </button>

      {processNoticeMutation.isError && (
        <ErrorState message={processNoticeMutation.error?.message || 'Failed to process notice'} />
      )}
    </div>
  );
};

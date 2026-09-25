import React, { useState } from 'react';
import { ErrorState } from '../components/ErrorState';
import { useMutation } from '@tanstack/react-query';

export const NoticeInput: React.FC = () => {
  const [text, setText] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);

  // Mock mutation for API
  const processNoticeMutation = useMutation({
    mutationFn: async (data: { text: string }) => {
      // API call placeholder
      return fetch('/api/process-notice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
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
        // Handle file upload here
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div className="flex flex-col h-[70vh] max-w-4xl mx-auto gap-4">
      <h2 className="font-sans text-xl uppercase tracking-widest border-b border-zinc-800 pb-2">Submit College Notice</h2>
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
        DROP FILE (.txt, .pdf, .docx) OR BROWSE
      </div>
      
      {fileError && <ErrorState message={fileError} />}

      <button
        disabled={text.length === 0 || processNoticeMutation.isPending}
        className="w-full bg-zinc-100 text-black py-4 uppercase font-bold tracking-widest disabled:opacity-50 disabled:bg-zinc-800 disabled:text-zinc-500 transition-colors border border-transparent"
        onClick={() => processNoticeMutation.mutate({ text })}
      >
        {processNoticeMutation.isPending ? 'PROCESSING...' : 'SUBMIT NOTICE'}
      </button>

      {processNoticeMutation.isError && (
        <ErrorState message={processNoticeMutation.error?.message || 'Failed to process notice'} />
      )}
    </div>
  );
};

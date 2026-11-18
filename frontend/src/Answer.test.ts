import {it,expect} from 'vitest';
import {mathMarkdown} from './Answer';
it('normalizes LaTeX delimiters and preserves code',()=>{
 expect(mathMarkdown('기호 \\(x\\) 유도 \\[y=x+1\\]')).toBe('기호 $x$ 유도 \n$$\ny=x+1\n$$\n');
 expect(mathMarkdown('`\\(code\\)`')).toBe('`\\(code\\)`');
});

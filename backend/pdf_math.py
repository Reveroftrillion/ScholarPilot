"""Conservative fraction-layout hints from actual PDF glyphs and vector bars.

This is not OCR or a mathematical reconstruction engine. Complex/nested or
rotated notation remains unverified; the original PDF is always authoritative.
"""
import re


def fraction_hints(page):
    glyphs=[]
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines',[]):
            if tuple(line.get('dir',(1,0)))!=(1,0):continue
            for span in line['spans']:
                for char in span['chars']:
                    if char['c'].strip():glyphs.append((char['bbox'],char['origin'],char['c'],span['size']))
    hints=[]
    for drawing in page.get_drawings():
        width=drawing.get('width')
        if width is None or width>1:continue
        for item in drawing['items']:
            if item[0]!='l':continue
            a,b=item[1:3];left,right=sorted((a.x,b.x));y=a.y
            if abs(a.y-b.y)>.25 or not 4<right-left<200:continue
            above=[];below=[]
            for box,origin,char,size in glyphs:
                middle=(box[0]+box[2])/2
                if not left-.5<=middle<=right+.5:continue
                delta=origin[1]-y
                if -1.4*size<delta<-1:above.append((box[0],char))
                if 1<delta<1.4*size:below.append((box[0],char))
            numerator=''.join(c for _,c in sorted(above));denominator=''.join(c for _,c in sorted(below))
            # Avoid treating diagram/table rules as mathematical fractions.
            if not numerator or not denominator:continue
            if not re.fullmatch(r'[A-Za-z0-9()|=+*,.\-]+',numerator+denominator):continue
            # Subscripts/superscripts need a richer layout parser. Restrict
            # hints to complete probability notation or plain numbers.
            simple=lambda value: value.startswith(('p(','P(')) or bool(re.fullmatch(r'[0-9.+*()\-]+',value))
            if not simple(numerator) or not simple(denominator):continue
            if numerator.count('(')!=numerator.count(')') or denominator.count('(')!=denominator.count(')'):continue
            prefix=[]
            for box,origin,char,size in glyphs:
                if left-100<box[0]<left and abs(origin[1]-(y+size*.25))<size*.22:
                    prefix.append((box[0],char))
            context=''.join(c for _,c in sorted(prefix))
            hint={'left_context':context,'numerator':numerator,'denominator':denominator,
                  'region':[max(0,left-105),max(0,y-23),min(page.rect.width,right+20),min(page.rect.height,y+23)],
                  'fraction_latex':r'\frac{'+numerator+'}{'+denominator+'}'}
            if hint not in hints:hints.append(hint)
    return hints[:12]


def readable_page(page):
    text='\n'.join(block[4].strip() for block in page.get_text('blocks',sort=True) if block[4].strip())
    hints=fraction_hints(page)
    for hint in hints:
        prefix=hint['left_context']
        # Only fuse an exact glyph sequence, in the same order as the PDF
        # text. The denominator comes from glyphs below this exact vector bar;
        # block sorting can place it before the numerator in extracted text.
        # Never fill symbols from a textbook-specific formula template.
        if not re.fullmatch(r'[pP]\([A-Za-z|,]+\)=',prefix):continue
        sequence=prefix+hint['numerator']
        pattern=r'\s*'.join(re.escape(char) for char in sequence)
        text=re.sub(pattern,lambda _:prefix+hint['fraction_latex'],text,count=1)
    return text,hints

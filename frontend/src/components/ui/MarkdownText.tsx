import { Text, type TextStyle, type StyleProp } from 'react-native';

type Segment =
  | { type: 'plain' | 'bold' | 'italic'; text: string }
  | { type: 'newline' };

function parse(raw: string): Segment[] {
  const segs: Segment[] = [];
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|\n)/gs;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(raw)) !== null) {
    if (m.index > last) segs.push({ type: 'plain', text: raw.slice(last, m.index) });

    if (m[0] === '\n') {
      segs.push({ type: 'newline' });
    } else if (m[0].startsWith('**')) {
      segs.push({ type: 'bold', text: m[2] });
    } else {
      segs.push({ type: 'italic', text: m[3] });
    }
    last = m.index + m[0].length;
  }

  if (last < raw.length) segs.push({ type: 'plain', text: raw.slice(last) });
  return segs;
}

interface Props {
  children: string;
  style?: StyleProp<TextStyle>;
  boldStyle?: StyleProp<TextStyle>;
  italicStyle?: StyleProp<TextStyle>;
  numberOfLines?: number;
}

export function MarkdownText({ children, style, boldStyle, italicStyle, numberOfLines }: Props) {
  const segs = parse(children ?? '');

  return (
    <Text style={style} numberOfLines={numberOfLines}>
      {segs.map((seg, i) => {
        if (seg.type === 'newline') return '\n';
        if (seg.type === 'bold')
          return (
            <Text key={i} style={[{ fontWeight: '700' }, boldStyle]}>
              {seg.text}
            </Text>
          );
        if (seg.type === 'italic')
          return (
            <Text key={i} style={[{ fontStyle: 'italic' }, italicStyle]}>
              {seg.text}
            </Text>
          );
        return <Text key={i}>{seg.text}</Text>;
      })}
    </Text>
  );
}

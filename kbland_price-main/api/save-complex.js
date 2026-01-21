// /api/save-complex.js
import { Client } from '@notionhq/client';

export default async function handler(req, res) {
  console.log('🚀 API 호출됨:', req.method);
  console.log('🔑 환경변수 확인 - NOTION_TOKEN 존재:', !!process.env.NOTION_TOKEN);
  console.log('🔑 환경변수 확인 - NOTION_DATABASE_ID 존재:', !!process.env.NOTION_DATABASE_ID);
  
  // CORS 헤더 설정
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    console.log('✅ OPTIONS 요청 처리됨');
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    console.log('❌ 잘못된 메서드:', req.method);
    return res.status(405).json({ message: 'Method not allowed' });
  }

  try {
    console.log('📝 요청 본문:', JSON.stringify(req.body, null, 2));
    
    // 환경변수 확인
    if (!process.env.NOTION_TOKEN) {
      console.error('❌ NOTION_TOKEN 환경변수가 설정되지 않음');
      return res.status(500).json({ 
        success: false, 
        message: 'Notion Token이 설정되지 않았습니다.',
        debug: 'NOTION_TOKEN 환경변수를 확인하세요.'
      });
    }
    
    if (!process.env.NOTION_DATABASE_ID) {
      console.error('❌ NOTION_DATABASE_ID 환경변수가 설정되지 않음');
      return res.status(500).json({ 
        success: false, 
        message: 'Database ID가 설정되지 않았습니다.',
        debug: 'NOTION_DATABASE_ID 환경변수를 확인하세요.'
      });
    }
    
    // Notion 클라이언트 초기화
    console.log('🔧 Notion 클라이언트 초기화 중...');
    const notion = new Client({
      auth: process.env.NOTION_TOKEN,
    });
    
    const { 
      complexName, 
      area, 
      pyeong, 
      type, 
      salePrice, 
      deposit, 
      loan, 
      result 
    } = req.body;
    
    console.log('📋 파싱된 데이터:', {
      complexName: complexName || 'undefined',
      area: area || 'undefined',
      pyeong: pyeong || 'undefined', 
      type: type || 'undefined',
      salePrice: salePrice || 'undefined',
      deposit: deposit || 'undefined',
      loan: loan || 'undefined',
      result: result || 'undefined'
    });

    // 단지명 검증
    if (!complexName || complexName.trim() === '') {
      console.log('❌ 단지명이 비어있음');
      return res.status(400).json({ 
        success: false, 
        message: '단지명이 필요합니다.' 
      });
    }

    console.log('📤 Notion에 저장 시도 중...');

    // 평형 정보 조합 (평수 + 타입)
    const pyeongInfo = `${pyeong || ''}평 ${type || ''}`.trim();
    console.log('🔤 평형 정보:', pyeongInfo);
    
    // 결과 값 매핑
    let resultSelect = null;
    if (result === 'both_possible') {
      resultSelect = { name: '가능' };
    } else if (result === 'sgi_only') {
      resultSelect = { name: 'SGI가능' };
    } else if (result === 'impossible') {
      resultSelect = { name: '불가' };
    }
    console.log('📊 결과 매핑:', result, '→', resultSelect);

    // 숫자 변환
    const kbPrice = salePrice ? Math.round(salePrice / 10000 * 10) / 10 : null;
    const depositEok = deposit ? Math.round(deposit / 10000 * 10) / 10 : null;
    const loanEok = loan ? Math.round(loan / 10000 * 10) / 10 : null;
    
    console.log('💰 변환된 금액:', {
      'KB시세': kbPrice + '억',
      '보증금': depositEok + '억', 
      '융자금': loanEok + '억'
    });

    // Notion API 호출할 properties 객체 생성
    const properties = {
      '단지명': {
        title: [
          {
            text: {
              content: complexName.trim(),
            },
          },
        ],
      },
      '조회일시': {
        date: {
          start: new Date().toISOString(),
        },
      },
    };

    // 선택적 필드 추가 (모두 Text 타입으로)
    if (pyeongInfo) {
      properties['평형'] = {
        rich_text: [
          {
            text: {
              content: pyeongInfo,
            },
          },
        ],
      };
    }

    if (kbPrice !== null) {
      properties['KB시세'] = {  // ← 정확한 필드명으로 수정
        rich_text: [
          {
            text: {
              content: `${kbPrice}억`,
            },
          },
        ],
      };
    }

    if (depositEok !== null) {
      properties['보증금'] = {
        rich_text: [
          {
            text: {
              content: `${depositEok}억`,
            },
          },
        ],
      };
    }

    if (loanEok !== null) {
      properties['융자금'] = {
        rich_text: [
          {
            text: {
              content: `${loanEok}억`,
            },
          },
        ],
      };
    }

    if (resultSelect) {
      properties['결과'] = {
        select: resultSelect,
      };
    }

    console.log('📋 Notion Properties:', JSON.stringify(properties, null, 2));

    // Notion Database에 데이터 저장
    console.log('🌐 Notion API 호출 시작...');
    const response = await notion.pages.create({
      parent: {
        database_id: process.env.NOTION_DATABASE_ID,
      },
      properties: properties,
    });

    console.log('✅ Notion에 데이터 저장 성공!');
    console.log('📄 생성된 페이지 ID:', response.id);

    res.status(200).json({
      success: true,
      message: '데이터가 성공적으로 저장되었습니다.',
      complexName: complexName,
      savedData: {
        평형: pyeongInfo,
        KB시세: kbPrice ? `${kbPrice}억` : null,
        보증금: depositEok ? `${depositEok}억` : null,
        융자금: loanEok ? `${loanEok}억` : null,
        결과: resultSelect?.name || null
      },
      notionPageId: response.id,
    });

  } catch (error) {
    console.error('❌ Notion 저장 오류:', error);
    console.error('오류 타입:', error.constructor.name);
    console.error('오류 상세:', error.message);
    console.error('오류 스택:', error.stack);
    
    // Notion API 특정 오류 처리
    if (error.code === 'object_not_found') {
      console.error('🔍 Database를 찾을 수 없음 - Database ID 확인 필요');
    } else if (error.code === 'unauthorized') {
      console.error('🔐 인증 실패 - Token 또는 권한 확인 필요');
    } else if (error.code === 'validation_error') {
      console.error('📝 데이터 형식 오류 - properties 구조 확인 필요');
    }
    
    res.status(500).json({
      success: false,
      message: '저장 중 오류가 발생했습니다.',
      error: error.message,
      errorCode: error.code || 'unknown',
      details: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    });
  }
}

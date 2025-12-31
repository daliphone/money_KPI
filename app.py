# --- [更新版] 資料輸入區：完整欄位 ---
if is_input_mode:
    st.markdown(f"### 📝 {selected_user} - 今日業績回報")
    st.info("💡 系統將自動計算「綜合指標分數」，請準確填寫。")

    with st.form("daily_input_full", clear_on_submit=True):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        
        st.markdown("---")

        # --- 第一區：核心營收 (權重佔比 55%) ---
        st.subheader("💰 財務與門號 (Core)")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100, help="權重 25%")
        in_number = c2.number_input("門號 (件)", min_value=0, step=1, help="權重 20%")
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100, help="權重 15%")
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100, help="權重 15%")

        # --- 第二區：硬體銷售 (權重佔比 40%) ---
        st.subheader("📱 硬體銷售 (Hardware)")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1, help="權重 15%")
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1, help="權重 10%")
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1, help="權重 10%")
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1, help="權重 5%")

        # --- 第三區：服務指標 (KPIs) ---
        st.subheader("🤝 顧客經營 (Service)")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        # --- 第四區：遠傳電信指標 (Telecom Metrics) ---
        st.subheader("📡 遠傳專案指標")
        t1, t2, t3 = st.columns(3)
        in_gap = t1.number_input("遠傳續約累積 GAP", step=1, help="請填寫數值")
        
        # 註：升續率與平續率通常是公式計算 (續約數/到期數)，但依您的需求開放手動填寫
        in_up_rate = t2.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1) / 100
        in_flat_rate = t3.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1) / 100

        st.markdown("---")
        
        # 提交按鈕
        submit = st.form_submit_button("🚀 提交並計算分數", use_container_width=True)

        if submit:
            # 1. 取得該員的目標值 (從 Session State 或預設值)
            # 這裡先用預設值模擬，實際運作會抓 Excel 裡該員的目標
            targets = st.session_state.targets 
            
            # 2. 自動計算「綜合指標」 (依照您提供的 115% 權重邏輯)
            # 邏輯：(實際/目標) * 權重。若目標為 0 則不計分以免報錯
            def calc_score(actual, target, weight):
                return (actual / target * weight) if target > 0 else 0

            score_profit = calc_score(in_profit, targets['毛利'], 0.25)
            score_number = calc_score(in_number, targets['門號'], 0.20)
            score_insur = calc_score(in_insur, targets['保險'], 0.15)
            score_acc = calc_score(in_acc, targets['配件'], 0.15)
            score_stock = calc_score(in_stock, targets['庫存'], 0.15)
            score_apple = calc_score(in_apple, 10, 0.10) # 假設蘋果目標 10
            score_ipad = calc_score(in_ipad, 4, 0.05)   # 假設平板目標 4
            score_vivo = calc_score(in_vivo, 10, 0.10)  # 假設 VIVO 目標 10

            # 綜合指標總分
            total_score = score_profit + score_number + score_insur + score_acc + score_stock + score_apple + score_ipad + score_vivo

            # 3. 建立資料物件 (完全對應 Excel 欄位順序)
            new_data = {
                '門市': selected_store,
                '人員': selected_user,
                '日期': input_date,
                '毛利': in_profit,
                '門號': in_number,
                '保險營收': in_insur,
                '配件營收': in_acc,
                '庫存手機': in_stock,
                '蘋果手機': in_apple,
                '蘋果平板+手錶': in_ipad,
                'VIVO手機': in_vivo,
                '生活圈': in_life,
                'GOOGLE 評論': in_review,
                '來客數': in_traffic,
                '遠傳續約累積GAP': in_gap,
                '遠傳升續率': in_up_rate,
                '遠傳平續率': in_flat_rate,
                '綜合指標': total_score  # 系統幫你算好的
            }

            # 4. 寫入資料庫 (模擬)
            st.session_state.records = pd.concat(
                [st.session_state.records, pd.DataFrame([new_data])], 
                ignore_index=True
            )
            
            # 5. 回饋顯示
            st.success(f"✅ 資料已儲存！")
            
            # 顯示綜合指標卡片
            score_col1, score_col2 = st.columns([1, 3])
            score_col1.metric("🏆 本日綜合指標", f"{total_score*100:.1f} 分")
            if total_score >= 1.0:
                score_col2.success("太棒了！今日業績達標 (100% 以上) 🎉")
            elif total_score >= 0.8:
                score_col2.warning("不錯喔！接近達標了 (80% - 99%)，再加油一點！ 💪")
            else:
                score_col2.error("今日進度落後 (<80%)，明日請補回缺口！ 🔥")
            
            # 顯示剛剛輸入的表格 (讓員工確認)
            st.dataframe(pd.DataFrame([new_data]), hide_index=True)

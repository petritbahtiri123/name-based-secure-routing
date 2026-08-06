from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections.abc import Mapping
from enum import IntEnum
from types import MappingProxyType
from typing import Any


REGISTRY_SOURCE_SHA256 = "6a2b1aef71f39392495c53e3cbc98caef0ea5a62a8e22f3bb0b8ff62a6ee3559"
_REGISTRY_SOURCE_B85 = (
    b"c-rk<TX)*XvVNamq2<?Ojju_Z+3P$ItR(CZU;t-!PSz|f8Dv{KLa-"
    b"$fhuLfX`>E=?gjy1qmhFU>T!hq@>aV}5uCA{B?=O~ha5Il*Uh01H<0P0z2ftY-hxm9A&u@azhyNc$*GX*O_)|ajQh3Fl`rqttCkN"
    b"!UB=yo|f^T^X_~e^E#h?9fzL@z@YV%UayZ1rtyEn1#|Aocgcwyp`=Uy1jC!}b1F%N^u3X5xnp%n&6>QAk2UbyrV%Zq)BS7KetN~{"
    b"5`#FFJCzgoR{<XZuJWi5Q@V1zHe6@9R<Ey@ShGD?HcN+x&y%!7|2sMVjO^O#l}``-fp-k<(TI}-c1(6Tu2vE%=RC-BVwp863=&<&"
    b">e_zQV#v7gB+kvAjqeCu2~!`8Ud?~&rzucVh;{Onmx>9P<0CV&4)zdx9G3-"
    b"3AzgLJh?i`@R3e>&~)XvZx(tW|gGYW%)G?EIfrHm62fFdnvgqd{xv^xB`@!LZ+dTiE?GBbATF(A%~<9$t;cZoB_+0RMf{>2}7Si`"
    b"sB*dI;M6-"
    b"q`uq*nQLKU3Pl!irVmEM*y8){~M;5o30jq1w8u;oVN3LNax*Z=uhVHv^j`=@K>#6dN+@QzX)6C>o)_?9{k<EkAR`?f`z_vGXTBxL"
    b";tp-+lF8%=z1J4ll09pnle?gJ4BYzLhMD!0_Z=QtlD?}<m+M{L}^j|FOAgSi6-"
    b"F^H45mr`At#1uZ+~&2K|YO7rL#j`NBxee*|gdC&>s3^zqxGnqM2KnKO(NP01*iFwC)GtTU!b^};_nX{HI3>;Mia7&nCtF{F<{BTR"
    b"?>H)flajK!I$32*~uXzF|mrZ5W%Dd*(eC=R>9jXzmULcgT*W>^m^gtfqmuwPIi|CdJPKlGD%xU6V`84heM7QPo=`ja3jul{03#?T"
    b"CS&%5>OSVLf~x$V}VMXbb*Q*5fgJi9PvD`skUTkQ|J7MMY3e}Kknf9MXKc7J&3{(j{QKkJ(CvXLeXozbA*8#%gGm;tHNyBzd8y>T"
    b"r;Tr|>zDnS_1-"
    b"hcF*;ply5z*mst&!xh6ecV_xDg^S{j4GG)ljUr=Fisn3LX{xS3@z<(S^eg!ciDBI2_T2jSl5E{CR$J~gcs(Ua5cDWjkOJUX}$q^e"
    b"ev4Rdgi^;{y<r(bRJxouDxpX&5&cK*X~}8(6_@UV#zExKR#}#5oMw{KQ=>);M^K@Mq}ycs}ja(W6dZRhZ%DGqciR~qmhd)Nav%|("
    b"~9BTq=um0-l~y!(MS`@N5Kp^4xLZ^Hf_M*YV=-L`76_vYkB$n_`-"
    b"DECA@ro{MvNw72|Hm;{z=4w%ci=S{U?)I^dt2n5|qt>V}*<V(Emeb2Ta*dPDx5d=sk1-"
    b"wgfze$|3~r*Ws}xV=7X0coo@<mZ6}+b0lxMdhYA53~)`?R@H7f*RD;{>t>~{T=AxVI2i@a?xm0$^rSh5vNAkO5yzUxWP7*u+*uc9"
    b"Y5!Db~hSy^P6r*tDa9!8)`<0B+eRYLOCwZ8*N3IJk0QBul3P!rKhI?7B8D<Lx~JtHBo;#ATF9~LYXAYaOS1cb>7t>h_hqU_3Qh7c"
    b"4E5jQUsixHdB3>1kM`qepf)?ypcwfNZ~~z4JZf0%Ldy}CW}|57j>h4_o@ytTr}2@5^0!W$JSurw7M0R_4%>cx=T&z^Ib(-"
    b"#=e(8?B`@Yt=hir^?QY_F(U?NI3y6b8nzv`+xgfTHy1XCbwgNXvG7lgRoTNZ#uoh9X}7w~#mQmSSH02I0KGZ5Ne-"
    b"J|x)z)pYe9SXc`)vyTlsCL>ogZEhjouS?|R@+89HvK_o>zGTs9Xght;DiVXTRpePygxT$v26hJ$`F%rA^q-"
    b"0i$|+MnCS1O3|EK*Ofi$5w;Uaabuht46wzd2{?Fwy_(Gf1@G>S4e{~Z-lG+U@?GG?q36lhu4YP9CZ!*-"
    b"R>Kmjq<{vb{uqDpBoHs!%D#-"
    b">hS%C2E*EjhUlZy`AP@r3xk6G)c@cVDuoksTs3xvA3Hs;1j#OEp(SFDv(%F%g;kp)E*W=FSg}Fo8bDy6`>EsnQCP7#`r_N!<M&|j"
    b"zVCMnk#=g1zuscC*n+}(%@G*iL~%cMMkCFcol|pE*1sCJ-Z@Np6xMBy%PzqK_-@#`ES}fqsH_Xr-"
    b"7V|#YlAGx_U%e+>@#zW27KZSdzy9Ct`^f@{gt~|#*2AUwV38MKNt`F23NLx5Sm-qvi-"
    b"r&WRazr<PB{AHMgM6I{BMh%u3gCb1PUiMzXmTZ06`|xBsrevtCqNH@I-+F5=71NI!c`9q-"
    b"!Ukn_oj;ee+Gm$L6r(7l!}#N*7guqnQE;Z^55)K?)tu~p^%h11o|DXLa`-"
    b"1+1*siwxAVWaAa)L6W#JU2FvG|SkXos4Iv0BeH^Haof<&C=S45MWk!-gbD{s-"
    b"w*naB8sj;{KXJ8Tivbb<ii)q(5IjdCizTqpJ}PrPH9_UIsy4HfQvdS??E3lav`_hkL!cpG)0t$A)@~DP%NN?ry`Co>O+AklQML6p"
    b"Q8(sxrG$bjvvF)M$_`xTVI!j&4BCb~YZ#GOU%&g}5zDq(3U-"
    b"Z;ZicH=I{U8`^$m{xC~(TB>vp@<rnW{?ceTO>;_$#;@#HMP+8}lw~(?=gV|5pH<qJ?Y1*$)W?Qeq`BEzq8d!CT*`Ra^q~`z>lZ(Q"
    b"q=FNY!pEIGwTLM27{j3#=MVQv6BTA?u#uk8S>4ucLz?OBu+`}`hiPValF&<Byy%3yE6<C^lO?&6&`T<}3&in~N7^^Y9B*lM1L4y7"
    b"<aGN3JmxD78x5NS#<~Nv$pnXW+}tmkc5|CP8`7Mu!uCrV41i++t$aQ;x3InhrHuqfQl*yEZvN0P59@Al3qfy_nm#PdH*Xr;MHsh+"
    b"@0>9Sm%_-j;`#LOErefKD{ukr$MB5{iPvuHWETD+YF31Q`r-xq_n-"
    b"B$0n1WeR+pkl*(%FW1G#jC=u(|2r9fc5(x;P`kQ}A3C{5J8Ea|L<Xf)9VN^@S+E2Pj{znOeX9sf#;YIIBQAd}^s*D0pZuOrK-"
    b"G2&$_&5h(!wy=-|)flcayRqiLi-`-"
    b"l0eygA7}7p2NZL*@dy!5ci|oXA<7Jr3vuVjh;v~)Z#EaqIQ)?cDD=UCGKlLp!`>oEUbwV<eM?fku{GR&pBK9#uI;1RbLn|ycwGJ&"
    b"hQQ_~{^5Yo(q&d`oJ>a9t+9FD~F%x=d)7NZhj7@5>v2*Mx|CaQ(AO$*28lTQV6g-"
    b"=}`lE%~3(f`{yC*sOnms;6+c!_lYiywuHw&U*ww&ckn|a^)(^qSy5n%|v*rcr2Yh~rg@PLc}eMpBhfy~Jh9G>fyH3@-"
    b"UrYyny(S+tyJ+z{E3K{C7<;;(R3Hz9%VnsE@-"
    b">TTTG}wqp(27<IW)NCYOmcx{G1G)OD6BLwo23CGjR{FRQs+tyC})cdoMuD7r=7e+K=g!YJGCQf=1OuxD@!Fo@^6xc`8O+#m%f;U%"
    b"jjz~zmKS3<TV0p5;ERdb1N|gQsejzQSLC!@36U3_4)#fsQVCRf}75jjudc=fKE;ui|6Y^DUrKIee$P_fgm2|R8r=-"
    b"(07`7Rt$3av_MaZA2Ui>d74#6$`6Wy$x&+(+(OoKS4t9Ys)&Q{a$q%?;T1|^MI?TzP8ZeUQ-`X~N*Q^MimxIt4_-"
    b"{~pnG@oaGI$*Ghx|(mH+)I{{8o1jrOiDF|#c!{9WI$(`>`eiW|mtp@j5&b{#}yZW9YQ3~iLT9sB=T!d)BFESYIC>OW}QDxEu7v6Q"
    b"^k#Hf|Ig7OF}dcpJn!u2UQfOY~;lAD0fO+J7{R}wsE^a}kJSwU#SL3c1@55)7@B?+cwQ5d4y5OfRNJ<T+3W6aw3L3(E=6VO-"
    b"L@hZMr;z5H};o;0mNE7W_Dx<Tkj9&a)8bfm%$AgBf#4Vg3uCf;&nR{~gg!~K=nFs*b*hg@?!77z?<S&@^bPb-"
    b"7(%P*iKdYP)DX1bjt=+-$AUW-rX&RYNn!8|jW1AK@va=E?J*Mzf6ujw1no#t)dvzW(ocisjtek2b`)F)POZTlFquEu19M3}-"
    b"<psDzZh}e0sAjJ!+K=s1AKNNpukZ#aWmvrsoZnd7H@{?D`Bq-"
    b")#kar~=ye59g?^mvtPUgj@(Rp=l0Cwrg?zyYtV)3w2t6<Otnk$V$P5A-hzJ~I9_Y38&K@KnFq=tBA=A33<noU2O4-"
    b"nsecF+@E0<Willa-"
    b"X#9!=2;`PM{_7{u<7_6|39Ib5J6?%q}JT)fCEOv`!M4asrY_r(jbZXCI+yB0RJv2MTWq<xnw%uc&9UlWbL2c9IU^{;Ezk8E3#P-"
    b"0tL~@n%deglj`nI|a1x|Ap3>qR!aE)^YR9)ckiW-VQJ_!<+fMLq^MY5p^!4&r{P&O{#lXBHot$o9HQ%GH6)8t6IN0JF?P*z;oYxE"
    b"jX%Y`RSpQ0i*)zAkzc6B!p{xDlA4>V1*_ap9RefUVb0f+m2u_xi>)Lwo0Aas>S4L+2X&Y!AZx}L-"
    b"Qfg@IUQ|N<6Yc0xhKR{azkc_OH&r=9kT7=#t>(Z2Q3_LnPX`&3I$;GmXh)!1o>J-"
    b"G`WW!d1XzDL~_yfMWrykbK!c|ilbd4a#6<t$JH53GRaAyHT7P-"
    b"&~Fz6tR$qQZ5;hDE0HeoJS1>R1A=+?!>a1broz=lEOLs*7=4Z#~<;b)r*gj&=>l#4j{=1o>E2rh!xq$F$dO(~EIks_m)GLm6Jbc;"
    b"SYEB*v9lZkvq@y&uXbI~}DcbNtdqmrsYD*u6as}urkG7&AoBES(9Fj9Ypg$9gR;(F;prWq*x(07+f*6u#I@q!TC^R6~liNBDIS;{"
    b"ZpU?iqNng@&+z^Q)&F>rtv9%`fn8vil4uxV;n8&h`UiFKUK_VG!E&_tB;HN*@eSY)5clPu32jJ@Qmb*ipd$dj|RC+BNVUaUQNd9c"
    b"O?yr<Bk5Ee7BcTGbZ=}6kw0AU(d2TN%mwt$Y73tSFa{5yn^MdOM{bR|S(K_MXv)w90Ar}J2eS4yEBCt~X35(#1{VVJ{ke!sT<;&{"
    b"Sfs0q$dwi<(f$q&f%%x=QKNc8%{k1aeyWz(gPb{J@AVJ4u8*$!eQYEwMhiy(qEqJ0NVhslZopUHd)QDrvSD1u*tNLiwipMXaqSPC"
    b"S_ng`SQBst<io<}kU^yq$ZVFSNLND8dX<kx>AOeJeC0e3K2M2s79;&&H0EQBCdmwuIHEBq|<y$Bg?#@>MM7Ryv8Z{_s>3&z>aR?t"
    b"~_i!XAo5eNgCuBpP)P6-"
    b">m2q6F|wh<9FM1S~eDDiIKclT}yGIZ&g056m?Qq@r+9FpTIAHs;uXTE@I4`7U~O8}t2;uEg<uoogsm%8ylzDuI<qGcEg6$UI0UF1"
    b"K#V9}p4Rv8PIv6^-+O88){)x04JnXKJXu3-1Zn*||}uMC8=z1!ILvt)dKM-"
    b"8GWOlw%ILX<S31=<8t+)~1*Mf;BEbUR{4EskXIN7vBVDGP(P$hcVPof4yq3e3koc=$gO%gds4e^tFUfY~@laG5V{MQjTnJk14sHS"
    b"v+B9##qoDJ3*_bEEjP4~UtwawlRZBv&v9kql&t%hyR9EEI9m5ZBo<6{eNa3}vLqds$c80l0W(i#gd|C&)xcGHr{^+CnA__~PafAs"
    b")s^>_rR#m4&gX>WXl3QX|0&2}eJ*`LGe`*qJUC#;#^2KqfZV2l-7>>a~vYn}<br-EWU$T-"
    b"*imEFr)nysW{qa1IiM6#F!!d>JLn#bO>KK4IjryP&1`%zN4>^(J5U7&U^?{Ec}u=|~|+xtR+6O4xEI578mDa}zj%!Xe5Xf)<alw&"
    b")_)!Yy|&RxO_#Umzn;1wv+R@P?@79R!P~Y*8nFuM11AHEldX7fk#TBtrkxepg|Uj9r3K0S`8T2h(|Weu=P-"
    b"OfpzaqpxT>V1NXnB`xrDf%Fdqqqu!%dpttOQlv6wOu+|uWNT3n(2Z|-*9nf0MIxFkI4VItp-P_&c@;FPA*8|HgE1|j34^?V1)1Lr"
    b"I-w^JSm7h$!1{k2s%#jnHrTsC$ku~4TZ*ALG9b?1C04?yJ_`}sl2Lht8D~^#mU5(6xNVj~FQh%N=hx@XueqSY4f!<>&2oONg-"
    b"*(^{8c!D8coS|F|4)X)gqnW#@^x%<poDlDV?Ts!mZ3DhR0P|-}V&y<5BFUc&$gV%H6fxeOX4cqB7_=`kT;;qUBkk_Ys-"
    b"=gc4auO~oM{3(j!{5it{xmKh!`67sa?*yqZz1!vO!XYF9trWS1hQp;Jl9#|>udJ?HIbXi60(HdI$dJ7mCw{C7NQ4=08XWs9<o%;i"
    b"k@NNLjD4Bpr%g7Slkm|bswjLYP<0GXOFL7{z&8v8~L?FI35Q{Z75iF35N4H;UI$uq(@wSexJvA31S$hm)LpsjGv@R9vkSe_k(wya"
    b"xrLF{F^9F!ux_;wZ`IEqJ$nCo4-e-hZ#<v7MTE0~e0E-"
    b"K<3qedGmF;VCLfKAM(L_(U9<^YBM#<Y2%fe$3f{pxpa4skt4(!*by>YPT(+YH|=hrtR(;NoNn6wTEi@1~l5m#R_;K=e>MEKK&Ub9"
    b"pw94}nT&yy@Sf+J%}*5O)Ic{RAigQ;7Bbg)eBaQmN=A(uJFDK4>8pdxNlCGo&BK`xDO+T-"
    b">K;Z_?tPz~DF1P|kc{uBfwmiYvl)EotAOneg5X|dQrxi$NrrAJ%^;xmG9ay}1F{#f2*;xAI~$s>BB_<@JO*^|O1Nn6AD?T?OVjt$"
    b"am8ZIay#ab-FfR&>P;)3ZiXMxI|mDa0FS7CW6v0BN77<Ue&&~qz+ycNx0HPdv!!QM*U6pWgjJsX;-"
    b"3ec*I)M~8d!wKlANfmiKcA!?&Ks82w5TjJdB=el;a9aclpQ-"
    b"4zPRn<C?e5ixT!Y9wQl)G8+H4r`tWFj<p=9g;i)E)mBrJ(eR?*BS$Bb+#xaY<^GILqGHsr*0)a{NK`Ib~Rlqv&1vYxLEx}Sz5smt"
    b"#<@#Cf_tmWH;<6k2<`%6-"
    b"u?UocLGKrgY?Wgy?A6e=BoCi}&C5~2NLZheQEL^gu#peRZwKRR38jA(kGewOct_b7uV11q2K@vbr_T2bvxp8wS)?!C?M%o>X!I6o"
    b"{6t)HCV0jH!PEda)I}U3lJZ+<hZCay7B*l4r3#a=2sui=(iZ%{R(e$Q~$vXI~u(_6{vo1EpdFiT15SkUPTyu+P4UtlmmZ#O<%4W5"
    b"d`Gk3Tlw<N1-Sf6&Gp#$g<|J8y#}Z^V-83+yE_^rMPj66>qiE14ml54hva4PW(lQlaAEi>!t3c%kmb2l{3|~CE)|9J%;d`eEC(t-"
    b"pLvj^%9~8M%3H(Pg1vJC3hPh`3;B4m6QW)bzwF%ML3eoW+_}D3R;C1{gGx52DtI_*n%*)Ji`aMwW62g|hNlb=dHuI+eZiy<yizWj"
    b"*g93X-"
    b"%1ty+d(&tEJ#E^Ukm7t^e$v8(t96YErPDP~tKAAM0c~avRJx<+_9Y3QX2+znh^8_;v}nqdLlwG*6xAtB1%l$;?|}XgJD^)Yx&Ef7"
    b"0^^cR&k`X24!cTt-5<+_qJouTkwimB4Bs?|2SF-kuc>#)dLOX&;}EPCedQ)^2>`j3%K^A%1yC63&R6e4_x9R<bM3Drgu~Rqnj9)D"
    b"_hkWOG3!YJAWh*23!oLV9SOVwQWLm-5q4+;|6brzEW?(OdZYwSJgLrybkz)wdDm>2o6D9N^U83HJ#Prbyp3Fh&&^qzO*UPP-fKLe"
    b"N90?KReiD_9Z)k?DuKcxRRZ+{HrehyhbTH2rhFHH7hVO-"
    b"4I#C+MxPTdc}Siny9#a{T#ag_`VkkjYAsQ=LBPxbk$ggYs92sX9Tm+bV3CVlo8iy>+2~!J=g+5g-"
    b"!{PygJ8`BKYA2uBl0BvSjHcEg1`RByR8p8KR2UONa|T8nAjMQ%<7cA))}3@U$x-!J-Cp;aeIBZr(%1M_U0)bV@xa@uml70Ag-RC!"
    b"j~%|MvgS8tm<hJdVT_Ks7E-"
    b"szb&5O(v)E0H$|mb*W+pTbrAfogwLe`5Nnk@zu#f^nDvzNPC|*N;u;G9QxDzz6sYVqmL9d%f@u%aW?{<l@(+=*o!DjKxjTTQQE>k"
    b"T-hCvV!5^Ksof2ScZ#j7ovLV<7DtA8N)$0#{_6X9Th6rs8i@A&EJd)*533EAATv~_L4Bo+v*U{}EqiGKoTo^DT*c<(>L~{764RDE"
    b"9PtLaW*A@{?xwVKq9@#Un5%?+8z&srfVJ&Y4>FkUEOJGhifa^0}$;_Da=A7#28qwbc26{~@LTgxddyBz|uGcVHF&2+vf_)w;R-"
    b"4g9J3O3rFp8-OY&RN6BcaU_mHkB7FI9kS4A)w#y>h&=go7-"
    b"Zs{&Se7WI&A<`VA4od_EDRCAwpYYU_f&>v~FC;IffqGh&$D&NyrQ+Ssq87@l+Pz#d-"
    b"kOSVF02VSB3ea_s6n8@ie;D&Zu**a8i2~|wi<!&{_&BHje?9`Ga;`(23Ox0@3AG@qiGLC3WU%DN0;8##6`&#7+;0~=4m9gWuY7Pm"
    b"XD|JR2*NkrjxLDstG_DeP2~UrH$U0^UN()Dg%YxH-nDH_Jhp{PR&g<#0m59+_U{?95|$tQRVLhZx7mQ#VW}m{DoAR0lB07Ck9(SY"
    b"mNdBy9v?!JWhUk(EGf;)btHmpL_mw&{Gy8eNzvxs&U~V*S!HQ%NuCJRy?wbS&T8W9wLUto%$QzkT#7{JHOZ5!aJ-{X$?Ko-"
    b"aIOgdZL(X1rP-vky@C0}GM(>=Cv%|GufuBrGQ*K<5iY=}e5mpx5soo>EQ9c#AdLfYYj!MkTW&~>s%5EgBURd9PfnN0u}h!jG=+OZ"
    b"AD15YhUAlD$4Y1A!%0%2lB00Xm3ywtapk4cb>7u*QOZklHuhAKRQYz~#qs=}rO0JPZNQ3|ix|lF{@##$OiUWO9!J5WmK$qgQM1Zc"
    b"u6t6=NW*LEO`*IeNwa|5iXqD^$t?&{nv#MX;pF`HMG&tJ=|OvO-p{*-1XU_@>$xkNC(ymA`DFOB%Ea6mjWR=X&!Bq-Eo9LAWxAz?"
    b"rnpOYQ!`U+&CnfjanUY~C#t=%BkJG$jOX6Ye0KNa=Ao%2%UZB3SdI%AK8nk7BUJARvk7c&Pn%`d=f<olZBK#F>wpITg5@c9BA*y<"
    b"?#;_5Nt;!s=7ZUjnV5Ux+!JSw3zK9LoKe4fRqfoo#Sosz%N+Px<4l>*SJ~g;$w4fc97Ns;7JDpegJ;vJ8M`i<vo}JYR&tS{808K5"
    b"R2kA5shb39wS-"
    b"!N*a8|YLTO`ES`W>84s8aL^;xtv7&xtN`N_!=7|Pq`77HJ8f`Ky=(}pEJq}qp$hb!wQp3mg@cy?lvWpq}K#&48CjM6fmEAzu}lLM"
    b"5rl{IsPHF$uMwQJ%f&nxRli?sWaW%S-"
    b"I2aZ5s*<r|12+|{vUa{_Gz!X`>(>u833&aHrBMS?SLBbX!w3|Vq=n$^*#0=UTm$+fH3~Ss<UkR&{Bn@j|KHT!a@8hJ)d4_s^JJi<"
    b"D@xL%sAFxhBn2<{VBtU(@nb0LC>s7GxTsQ7LjFIw#vQBYj5{KVpY7-8MzeN`y`NDND1uN8@!+^*4L4qH^)wsTRh1^*ix&-"
    b"OIE7O*^$k()V{h5FE6?)`d*6bXx5nFC9pM(l*Jmn7$uS4HeZuiN&K{Keia(gWEvrIwZ@{9r5iNi8dxG=9`koZ(go!n4`P<rUz&*Q"
    b"H*05giMg7H#E>K^**@~H_w+<0N)XD3Te98A3`GQ{OIOWd)ZK7_L35JorqtUd00YUN7d<MgrL>%cKdNKK;t+U|cGbRF;~Wxn{QL&j"
    b"4hk#)4Wi9f^iOcO;g!nKq^*1<ADdkcUUyFo-IhypH(E3Ey<84g{rg&`l%RcHM9D4N@XUZh^=qEHmUOM+cX7dP|a2A=4aDN|*?A1A"
    b"jz{Rc3+CF#P-"
    b"Q8m{^bR_t705sFf<_!S6K&~Lx0+A5~ZlL5qEvR#wj$*+n9+##SVlNTvgw@cdLKU~deAhzDWNSu*b@0~1R##g&yQ0fp1mQf-@=8-"
    b"+KO1Boq%;iZC=F)*5iUc>O&#Q0B}-R<6^h7qw2gpX-"
    b"2|bpsP)1|P)?Is>}8F~l3uh3myLin$>hDuHe_@)!eOr%4I2p7hCA==Wl}sc@S6p{K}8V^3yZ2xmI+i#jF80~q_xuJS9@UPd>zQVy"
    b"ofsBbkG43i`-"
    b"dJoGVLPJ<(aVylMkRIE@3mC7`e&SzRZRxv3Tk)gA7dRzyb0wQbxPZZk=6`p2*i0a61FqdDSJsFYmul)Yfy8Gh`*T<D_G`_%uiO>M"
    b"H4bUwRIfFONBJ!sQ_KARNX<iObYfjmcVYxoDviU&S{T6`x++?~RVCD>Gn#g@5BiM>YIRM?E1simF(!iPnZ>!E)1qOUO48SO|6L8@"
    b"Y1=HvfO*ms0n@b<7f`!2Y>%iE?zm)J5#1h1T1hf>QVswkxvQPgoE&6jCNA%2a5SSvfPqsz<7w@)SJy#9CU6`bYvFJ*;D&Ql&1rR!"
    b"5EBJ+$+P32L+R9b7H;QTL--V~MfOGRbADOoM>#Yi0r&wnXL*OtX|s{SG$7Lw~1^&>%pU;fN+R8}|W<~hlzCe+74K3(6zTIY*r?|M"
    b"o<t@PaDxm&PqDkx&@ouZ*w`!4w!EYPx!=V5q_F4S7~v^4L3`TLju2V_gU#{"
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _load_canonical_tables() -> Mapping[str, Any]:
    try:
        payload = zlib.decompress(base64.b85decode(_REGISTRY_SOURCE_B85))
    except (ValueError, zlib.error) as exc:
        raise RuntimeError("Embedded Federation registry source is invalid") from exc
    if hashlib.sha256(payload).hexdigest() != REGISTRY_SOURCE_SHA256:
        raise RuntimeError("Federation registry source digest mismatch")
    return _freeze(json.loads(payload))


_CANONICAL_SOURCE = _load_canonical_tables()
RESERVED_RANGES = _CANONICAL_SOURCE["reserved_ranges"]
CORE_COLLISION_PROOF = _CANONICAL_SOURCE["core_collision_proof"]
UNKNOWN_VALUE_POLICY = _CANONICAL_SOURCE["unknown_value_policy"]
SIGNER_AUTHORITY_MATRIX = _CANONICAL_SOURCE["signer_authority_matrix"]
ROOT_REPLACEMENT = _CANONICAL_SOURCE["root_replacement"]
PRIVACY_OPENING = _CANONICAL_SOURCE["privacy_opening"]
MESSAGE_REGISTRY_POLICY = _CANONICAL_SOURCE["message_registry_policy"]
MESSAGE_SEMANTICS = _CANONICAL_SOURCE["message_semantics"]
CONTEXTUAL_RULES = _CANONICAL_SOURCE["contextual_rules"]
LOCAL_WORKFLOW_STATES = _CANONICAL_SOURCE["local_workflow_states"]
OPERATOR_LIFECYCLE_SEMANTICS = _CANONICAL_SOURCE["operator_lifecycle_semantics"]


class ExtensionId(IntEnum):
    FEDERATION = 1


class CapabilityId(IntEnum):
    FEDERATION_OBJECTS = 1
    FEDERATION_AUTHORIZATION = 2
    TRANSPARENCY_PROOFS = 3
    STATIC_TRUST_COMPATIBILITY = 4
    FEDERATION_CONTEXT_BINDING = 5


class ObjectType(IntEnum):
    OperatorRegistryRecord = 1
    KeyAuthorizationRecord = 2
    NameOwnershipRecord = 3
    DelegationRecord = 4
    FederationTrustBundle = 5
    TransparencyCheckpoint = 6
    InclusionProof = 7
    ConsistencyProof = 8
    WitnessStatement = 9
    OperatorEndpointRecord = 10
    FederationAuthorityProof = 11
    FederationAuthorizationContext = 12
    TypedRevocationRecord = 13
    ConflictEvidence = 14
    OperatorLifecycleRecord = 15
    RecoveryTransitionRecord = 16
    ConflictResolutionRecord = 17
    AppealDecisionRecord = 18


class MessageType(IntEnum):
    FED_CAPABILITIES = 16_384
    FED_CAPABILITIES_ACK = 16_385
    OPERATOR_RECORD_QUERY = 16_386
    OPERATOR_RECORD_RESPONSE = 16_387
    ENDPOINT_RECORD_QUERY = 16_388
    ENDPOINT_RECORD_RESPONSE = 16_389
    OWNERSHIP_AUTHORITY_QUERY = 16_390
    OWNERSHIP_AUTHORITY_RESPONSE = 16_391
    AUTHORITY_PROOF_QUERY = 16_392
    AUTHORITY_PROOF_RESPONSE = 16_393
    TRUST_BUNDLE_REQUEST = 16_394
    TRUST_BUNDLE_RESPONSE = 16_395
    TRUST_BUNDLE_UPDATE = 16_396
    TRUST_BUNDLE_ACK = 16_397
    CHECKPOINT_QUERY = 16_398
    CHECKPOINT_RESPONSE = 16_399
    INCLUSION_PROOF_REQUEST = 16_400
    INCLUSION_PROOF_RESPONSE = 16_401
    CONSISTENCY_PROOF_REQUEST = 16_402
    CONSISTENCY_PROOF_RESPONSE = 16_403
    WITNESS_STATEMENT = 16_404
    AUTHORIZATION_REQUEST = 16_405
    AUTHORIZATION_RESPONSE = 16_406
    REVOCATION_PUSH = 16_407
    REVOCATION_ACK = 16_408
    REVOCATION_QUERY = 16_409
    REVOCATION_RESPONSE = 16_410
    CONFLICT_REPORT = 16_411
    CONFLICT_ACK = 16_412
    OPERATOR_STATUS_QUERY = 16_413
    OPERATOR_STATUS_RESPONSE = 16_414
    QUARANTINE_NOTICE = 16_415
    RECOVERY_NOTICE = 16_416
    REENTRY_EVIDENCE = 16_417
    OPERATOR_REGISTRATION_REQUEST = 16_418
    OPERATOR_REGISTRATION_RESPONSE = 16_419
    OPERATOR_RECORD_UPDATE = 16_420
    OPERATOR_RECORD_UPDATE_ACK = 16_421
    KEY_AUTHORIZATION_PUBLISH = 16_422
    KEY_AUTHORIZATION_ACK = 16_423
    KEY_AUTHORIZATION_UPDATE = 16_424
    KEY_AUTHORIZATION_UPDATE_ACK = 16_425
    NAME_OWNERSHIP_PUBLISH = 16_426
    NAME_OWNERSHIP_ACK = 16_427
    NAME_OWNERSHIP_UPDATE = 16_428
    NAME_OWNERSHIP_UPDATE_ACK = 16_429
    DELEGATION_PUBLISH = 16_430
    DELEGATION_ACK = 16_431
    DELEGATION_UPDATE = 16_432
    DELEGATION_UPDATE_ACK = 16_433
    ENDPOINT_RECORD_PUBLISH = 16_434
    ENDPOINT_RECORD_ACK = 16_435
    ENDPOINT_RECORD_UPDATE = 16_436
    ENDPOINT_RECORD_UPDATE_ACK = 16_437
    CONFLICT_RESOLUTION_PUBLISH = 16_438
    CONFLICT_RESOLUTION_ACK = 16_439
    APPEAL_REQUEST = 16_440
    APPEAL_RESPONSE = 16_441


class ReasonCode(IntEnum):
    NONE = 0
    ERR_RESOURCE_LIMIT = 1
    ERR_PARSE = 2
    ERR_NON_CANONICAL = 3
    ERR_UNSUPPORTED_CRITICAL = 4
    ERR_CRYPTO_PROFILE = 5
    ERR_SIGNATURE_INVALID = 6
    ERR_IDENTITY = 7
    ERR_KEY_PURPOSE = 8
    ERR_KEY_LIFECYCLE = 9
    ERR_SCHEMA = 10
    ERR_VERSION = 11
    ERR_AUTHORITY = 12
    ERR_SCOPE = 13
    ERR_POLICY_EXPANSION = 14
    ERR_ROLLBACK = 15
    ERR_REPLAY = 16
    ERR_EQUIVOCATION = 17
    ERR_CONTINUITY = 18
    ERR_REVOKED = 19
    ERR_TERMINAL_STATE = 20
    ERR_TRANSPARENCY = 21
    ERR_CHECKPOINT = 22
    ERR_SPLIT_VIEW = 23
    ERR_WITNESS_THRESHOLD = 24
    ERR_FRESHNESS = 25
    ERR_EVIDENCE_MISSING = 26
    ERR_OUTAGE_POLICY = 27
    ERR_DOWNGRADE = 28
    ERR_LOCAL_POLICY = 29
    ERR_RECOVERY_INVALID = 30
    ERR_INTERNAL = 31


class KeyPurpose(IntEnum):
    IDENTITY_ROOT = 1
    RECOVERY = 2
    REGISTRY_SIGNING = 3
    KEY_AUTHORIZATION = 4
    NAME_OWNERSHIP = 5
    DELEGATION = 6
    TRUST_BUNDLE = 7
    TRANSPARENCY_LOG = 8
    WITNESS = 9
    ENDPOINT_DISCOVERY = 10
    FEDERATION_AUTHORIZATION = 11
    REVOCATION = 12
    GOVERNANCE = 13
    FEDERATION_TRANSPORT = 14


class KeyLifecycle(IntEnum):
    NEXT = 1
    ACTIVE = 2
    RETIRING = 3
    RETIRED = 4
    REVOKED = 5


class OperatorLifecycle(IntEnum):
    APPLIED = 1
    VERIFICATION_PENDING = 2
    VERIFIED = 3
    PROVISIONAL = 4
    ACTIVE = 5
    SUSPENDED = 6
    QUARANTINED = 7
    RECOVERY = 8
    RETIRED = 9
    TERMINALLY_REVOKED = 10
    REJECTED = 11


class RecoveryStage(IntEnum):
    RECOVERY_PENDING = 1
    RECOVERY_VERIFIED = 2
    REENTRY_RESTRICTED = 3


class ResultType(IntEnum):
    VALIDATION = 1
    PUBLICATION = 2
    QUERY = 3
    AUTHORIZATION = 4
    LIFECYCLE = 5
    RECOVERY = 6
    CONFLICT = 7
    APPEAL = 8


class DecisionOutcome(IntEnum):
    ACCEPT = 1
    REJECT = 2
    PENDING = 3
    RESTRICTED = 4
    QUARANTINE = 5


class EnforcementMode(IntEnum):
    NONE = 0
    DENY_NEW_USE = 1
    REAUTHENTICATE = 2
    DRAIN = 3
    TERMINATE_ACTIVE_USE = 4


class AuthorityClass(IntEnum):
    OPERATOR_IDENTITY_ROOT = 1
    OPERATOR_RECOVERY = 2
    DEVELOPMENT_REGISTRAR = 3
    FEDERATION_AUTHORITY = 4
    TRANSPARENCY_LOG = 5
    WITNESS = 6
    NAME_OWNER = 7
    DELEGATE = 8
    SOURCE_OPERATOR = 9
    DESTINATION_OPERATOR = 10
    CONFLICT_RESOLUTION = 11
    APPEAL = 12
    OPERATOR_ENDPOINT = 13
    TARGET_CONTROLLER = 14


REGISTRY_TYPES: tuple[type[IntEnum], ...] = (
    ExtensionId,
    CapabilityId,
    ObjectType,
    MessageType,
    ReasonCode,
    KeyPurpose,
    KeyLifecycle,
    OperatorLifecycle,
    RecoveryStage,
    ResultType,
    DecisionOutcome,
    EnforcementMode,
    AuthorityClass,
)
